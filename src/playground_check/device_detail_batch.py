"""Load device detail data in bounded batches instead of per-device queries."""
from collections import defaultdict
from . import inspection_defect_repository as repository
from .remaining_reads_repository import inspection_type_rows
from .playground_detail_serializers import criterion_dict, report_dict, playdevice_feature
from .inspection_defect_service import inspection_history, defect_payload
from .inspection_submission import GROUPS


def criteria_for_devices(db, fids, inspection_type):
    """Three whitelisted criteria relations; the number of queries is constant."""
    result = {}
    for view, column, _ in GROUPS:
        rows = db.execute(f'''SELECT fid_spielgeraet AS playdevice_fid,
            bereich AS realm, pruefung AS check_text, wartung AS maintenance,
            {column} AS inspection_type, pruefung_kurztext AS check_short_text
            FROM "{view}" WHERE fid_spielgeraet=ANY(%s) AND {column}=%s
            ORDER BY fid_spielgeraet, bereich, pruefung_kurztext, pruefung, wartung''',
            (fids, inspection_type)).fetchall()
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['playdevice_fid']].append(row)
        result[view] = grouped
    return result


def recent_reports_for_devices(db, fids, types):
    return db.execute('''WITH recent AS (
        SELECT fid_spielgeraet, inspektionsart, tid_inspektion,
            row_number() OVER (PARTITION BY fid_spielgeraet, inspektionsart
                ORDER BY max(datum_inspektion) DESC, tid_inspektion DESC) AS position
        FROM "wgr_sp_insp_bericht"
        WHERE fid_spielgeraet=ANY(%s) AND inspektionsart=ANY(%s)
        GROUP BY fid_spielgeraet, inspektionsart, tid_inspektion
    ) SELECT r.tid, r.inspektionsart AS inspection_type,
        r.datum_inspektion AS inspection_date, r.kontrolleur AS inspector,
        r.pruefung_text AS inspection_text, r.pruefung_erledigt AS inspection_done,
        r.pruefung_kommentar AS inspection_comment, r.wartung_text AS maintenance_text,
        r.wartung_erledigung AS maintenance_done, r.wartung_kommentar AS maintenance_comment,
        r.fallschutz AS fall_protection, r.tid_inspektion AS inspection_tid,
        r.fid_spielgeraet AS playdevice_fid, r.fid_geraet_detail AS playdevice_detail_fid
        FROM "wgr_sp_insp_bericht" r JOIN recent g
          ON r.fid_spielgeraet=g.fid_spielgeraet AND r.inspektionsart=g.inspektionsart
          AND r.tid_inspektion=g.tid_inspektion
        WHERE g.position <= 2
        ORDER BY r.fid_spielgeraet, r.inspektionsart, g.position, r.tid''', (fids, types)).fetchall()


def defects_for_devices(db, fids):
    # Legacy completion/creator IDs may be varchar; never cast untrusted text to bigint.
    rows = db.execute('''SELECT m.*,
        trim(concat_ws(' ', creator.vorname, creator.nachname)) AS created_by_name,
        trim(concat_ws(' ', finisher.vorname, finisher.nachname)) AS done_by_name
        FROM (''' + repository.DEFECT_SELECT + ''') m
        LEFT JOIN "wgr_sp_kontrolleur" creator ON creator.fid::text=NULLIF(btrim(m.created_by_fid::text), '')
        LEFT JOIN "wgr_sp_kontrolleur" finisher ON finisher.fid::text=NULLIF(btrim(m.done_by::text), '')
        WHERE m.playdevice_fid=ANY(%s) AND m.date_done IS NULL
        ORDER BY m.playdevice_fid, m.tid''', (fids,)).fetchall()
    histories = defaultdict(list)
    if rows:
        for row in db.execute('''SELECT id, tid_mangel, geaendert_am AS changed_at,
                geaendert_durch_fid AS changed_by_fid, geaendert_durch_name AS changed_by_name,
                vorher_fid AS previous_fid, vorher_name AS previous_name,
                nachher_fid AS new_fid, nachher_name AS new_name
                FROM "wgr_sp_mangel_zuweisung_hist" WHERE tid_mangel=ANY(%s)
                ORDER BY geaendert_am DESC, id DESC''', ([r['tid'] for r in rows],)).fetchall():
            histories[row['tid_mangel']].append({
                'id': row.get('id'), 'changedAt': row.get('changed_at'),
                'changedByFid': row.get('changed_by_fid') or -1,
                'changedByName': row.get('changed_by_name') or '',
                'previousUserFid': row.get('previous_fid') or -1,
                'previousUserName': row.get('previous_name') or '',
                'newUserFid': row.get('new_fid') or -1, 'newUserName': row.get('new_name') or ''})
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['playdevice_fid']].append(defect_payload(row, picture_rows=[],
            created_by_name=row['created_by_name'], done_by_name=row['done_by_name'],
            assignment_history=histories[row['tid']]))
    return grouped


def build_devices(db, devices, inspection_type, with_defects, with_inspections, min_date):
    devices = [d for d in devices if not d.get('not_to_be_checked')]
    if not devices:
        return {}
    fids = [d['fid'] for d in devices]
    criteria, reports, types = {}, defaultdict(list), []
    if with_inspections:
        criteria = criteria_for_devices(db, fids, inspection_type.rsplit(' (', 1)[0])
        types = [f"{r['value']} ({r['short_value']})" for r in inspection_type_rows(db)]
        for row in recent_reports_for_devices(db, fids, types):
            reports[(row['playdevice_fid'], row['inspection_type'])].append(row)
    defects = defects_for_devices(db, fids) if with_defects else {}
    result = {}
    for device in devices:
        fid = device['fid']
        last, previous = inspection_history(db, fid, types,
            load_reports=lambda db, fid, kind: reports[(fid, kind)], serialize_report=report_dict)
        groups = [[criterion_dict(r) for r in criteria.get(view, {}).get(fid, [])] for view, _, _ in GROUPS]
        result[fid] = playdevice_feature(device, general=groups[0], main=groups[1], secondary=groups[2],
            last=last, previous=previous, defects=defects.get(fid, []) if with_defects else None,
            min_date=min_date)
    return result
