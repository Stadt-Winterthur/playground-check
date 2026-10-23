from __future__ import annotations

import base64
import binascii
from datetime import date, datetime
from email.errors import HeaderParseError
from email.headerregistry import Address
from http.cookies import SimpleCookie
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import urlopen

from psycopg import Connection

from .auth import EMAIL, GIVEN_NAME, NAME, ROLE, decode_token, hash_passphrase, issue_token, verify_passphrase
from .config import settings
from .db import connect
from .http import Request, Response


UNAUTHORIZED = "Sie sind entweder nicht als Kontrolleur in der Spielplatzkontrolle-Datenbank erfasst oder Sie haben keine Zugriffsberechtigung."
DOTNET_MIN_DATE = "0001-01-01T00:00:00"
VALID_ROLES = {"administrator", "inspector", "maintenance"}
DOCUMENT_NAME_MARKER = b"\n%PLAYGROUND-CHECK-FILENAME:"
DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_REQUEST_MAX_BYTES = 25 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _document_parts(value: bytes | bytearray | memoryview | None) -> tuple[bytes, str]:
    data = bytes(value or b"")
    index = data.rfind(DOCUMENT_NAME_MARKER)
    if index < 0:
        return data, ""
    encoded = data[index + len(DOCUMENT_NAME_MARKER):].splitlines()[0].strip()
    try:
        name = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return data, ""
    return data[:index], name


def _document_with_name(value: bytes, name: str) -> bytes:
    content, _ = _document_parts(value)
    encoded = base64.urlsafe_b64encode(name.strip().encode("utf-8")).rstrip(b"=")
    return content + DOCUMENT_NAME_MARKER + encoded + b"\n"


def _document_name_from_tail(value: bytes | bytearray | memoryview | None, fallback: str) -> str:
    _, name = _document_parts(value)
    return name or fallback


def _document_storage(kind: str) -> tuple[str, str] | None:
    if kind == "abnahme":
        return "wgr_sp_abnahmen", "abnahmedokument"
    if kind == "zertifikat":
        return "wgr_sp_zertifikat", "zertifikatsdokument"
    return None


VALID_RESPONSIBILITIES = {
    "Revier Mitte", "Revier Süd", "Revier West", "Revier Ost", "Dispo",
    "Revier", "Spielplatzverantwortlicher", "Projektleiter",
}

USER_SELECT = '''SELECT fid, nachname AS last_name, vorname AS first_name,
    trim(lower(e_mail)) AS email, pwd, letzter_anmeldeversuch AS last_login_attempt,
    CURRENT_TIMESTAMP(0)::TIMESTAMP AS database_time, rolle AS role,
    zustaendigkeit AS responsibility, aktiv AS active, is_new
    FROM "wgr_sp_kontrolleur"'''

DEFECT_SELECT = '''SELECT tid, fid_spielgeraet AS playdevice_fid,
    id_dringlichkeit AS priority, beschrieb AS description,
    datum_erledigung AS date_done, fid_erledigung AS done_by,
    bemerkunng AS comment, datum AS date_creation,
    id_zustaendig_behebung AS responsible_body_id,
    fid_zustaendig_kontrolleur AS responsible_user_fid,
    auftrag_status AS assignment_status,
    datum_auftrag_zugewiesen AS assignment_created,
    datum_auftrag_angenommen AS assignment_accepted,
    datum_auftrag_abgelehnt AS assignment_rejected,
    bemerkung_auftrag AS assignment_comment,
    infomail_gesendet_am AS info_mail_sent_at,
    infomail_empfaenger AS info_mail_recipient_name,
    fid_erfassung AS created_by_fid
    FROM "wgr_sp_insp_mangel"'''


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _date_value(value: Any) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return date.fromisoformat(text[:10])


def _user_dict(row: Mapping[str, Any], include_password: bool = False) -> dict[str, Any]:
    return {
        "fid": row.get("fid", -1),
        "lastName": (row.get("last_name") or "").strip(),
        "firstName": (row.get("first_name") or "").strip(),
        "mailAddress": (row.get("email") or "").strip().lower(),
        "passPhrase": row.get("pwd", "") if include_password else "",
        "active": bool(row.get("active")),
        "role": row.get("role") or "",
        "responsibility": row.get("responsibility") or "",
        "errorMessage": "",
        "isNew": bool(row.get("is_new")),
    }


def _request_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raw_cookie = request.headers.get("Cookie", "")
    if raw_cookie:
        try:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get(settings.auth_cookie_name)
            if morsel:
                return morsel.value
        except Exception:
            pass
    return ""


def _auth_cookie(token: str, *, clear: bool = False) -> tuple[str, str]:
    path = settings.base_path or "/"
    parts = [f"{settings.auth_cookie_name}={token}", f"Path={path}", "HttpOnly", "SameSite=Strict"]
    if settings.token_issuer.lower().startswith("https://"):
        parts.append("Secure")
    if clear:
        parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"] )
    else:
        parts.append("Max-Age=28800")
    return ("Set-Cookie", "; ".join(parts))


def token_user(request: Request, role: str | None = None) -> dict[str, Any] | None:
    token = _request_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    result = {
        "fid": -1,
        "mailAddress": str(payload.get(EMAIL, "")).strip().lower(),
        "firstName": str(payload.get(GIVEN_NAME, "")),
        "lastName": str(payload.get(NAME, "")),
        "role": str(payload.get(ROLE, "")),
        "active": True,
    }
    if not result["mailAddress"] or (role and result["role"] != role):
        return None
    return result


def current_user(request: Request, role: str | None = None, dry_run: bool = False) -> dict[str, Any] | None:
    # The original getAuthorizedUser deliberately returns null for dry runs.
    if dry_run:
        return None
    claimed = token_user(request, role)
    if not claimed:
        return None
    with connect() as db:
        row = db.execute(USER_SELECT + " WHERE trim(lower(e_mail))=%s", (claimed["mailAddress"],)).fetchone()
    if not row or not row["active"]:
        return None
    user = _user_dict(row)
    if role and user["role"] != role:
        return None
    return user


def require_token(request: Request, role: str | None = None) -> tuple[dict[str, Any] | None, Response | None]:
    user = token_user(request, role)
    return (user, None) if user else (None, Response.text(UNAUTHORIZED, 401))


def require_user(request: Request, role: str | None = None) -> tuple[dict[str, Any] | None, Response | None]:
    user = current_user(request, role, _bool(request.query.get("dryRun")))
    return (user, None) if user else (None, Response.text(UNAUTHORIZED, 401))


def _valid_mail_address(value: str) -> bool:
    try:
        parsed = Address(addr_spec=value)
    except (TypeError, ValueError, HeaderParseError, IndexError):
        return False
    return parsed.addr_spec == value


def login(request: Request) -> Response:
    body = request.json()
    if not isinstance(body, dict) or body.get("mailAddress") is None:
        return Response.text("Keine oder falsche Login-Daten.", 400)
    email = str(body.get("mailAddress", "")).lower().strip()
    password = body.get("passPhrase")
    if (
        not email
        or any(char.isspace() for char in email)
        or not _valid_mail_address(email)
        or not isinstance(password, str)
        or not password.strip()
    ):
        return Response.text("Keine oder falsche Login-Daten.", 400)
    dry_run = _bool(request.query.get("dryRun"))
    try:
        with connect() as db:
            row = None if dry_run else db.execute(
                USER_SELECT + " WHERE trim(lower(e_mail))=%s", (email,)
            ).fetchone()
            if row:
                if row.get("last_login_attempt") is not None:
                    elapsed = (row["database_time"] - row["last_login_attempt"]).total_seconds()
                    if elapsed < 3:
                        response = Response.text("Zu viele Login-Versuche. Bitte versuchen Sie es in Kürze erneut.", 429)
                        response.headers.append(("Retry-After", str(max(1, 3 - int(elapsed)))))
                        return response
                db.execute(
                    "UPDATE \"wgr_sp_kontrolleur\" SET letzter_anmeldeversuch=CURRENT_TIMESTAMP "
                    "WHERE trim(lower(e_mail))=%s", (email,),
                )
                password_ok, needs_upgrade = verify_passphrase(row.get("pwd") or "", password, email)
                if password_ok and row.get("active"):
                    if needs_upgrade:
                        db.execute(
                            "UPDATE \"wgr_sp_kontrolleur\" SET pwd=%s WHERE trim(lower(e_mail))=%s",
                            (hash_passphrase(password, email), email),
                        )
                    user = _user_dict(row)
                    user["lastName"] = user["lastName"] or "Nachname unbekannt"
                    user["firstName"] = user["firstName"] or "Vorname unbekannt"
                    token = issue_token(user)
                    response = Response.json({"securityTokenString": token, "user": user})
                    response.headers.append(_auth_cookie(token))
                    return response
                return Response.text("Keine oder falsche Login-Daten.", 401)

            # Preserved original quirk: dryRun also reaches this insert branch.
            db.execute(
                '''INSERT INTO "wgr_sp_kontrolleur"
                    (nachname, vorname, e_mail, pwd, rolle, aktiv, is_new)
                    VALUES (%s, %s, %s, %s, 'inspector', false, true)''',
                (body.get("lastName") or "", body.get("firstName") or "", email, hash_passphrase(password, email)),
            )
        return Response.text(
            UNAUTHORIZED + "Der Administrator wird informiert und wird Ihnen gegebenenfalls den Zugriff gewähren.", 401
        )
    except Exception:
        return Response.text("Ein kritischer Fehler ist aufgetreten. Bitte kontaktieren Sie den Administrator.", 400)



def get_current_account(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    return Response.json(user)


def logout(request: Request) -> Response:
    response = Response(b"", 204, "application/json; charset=utf-8")
    response.headers.append(_auth_cookie("", clear=True))
    return response

def get_users(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    email = request.query.get("email", "").strip().lower()
    sql, params = USER_SELECT, ()
    if email:
        sql += " WHERE trim(lower(e_mail))=%s"
        params = (email,)
    sql += " ORDER BY vorname, nachname"
    with connect() as db:
        rows = db.execute(sql, params).fetchall()
    return Response.json([_user_dict(row) for row in rows if row.get("email")])


def get_assignable_users(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        rows = db.execute(USER_SELECT + " WHERE aktiv=true ORDER BY vorname, nachname").fetchall()
    return Response.json([_user_dict(row) for row in rows])


def update_user(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    body = request.json()
    if not isinstance(body, dict):
        return Response.json({"errorMessage": "SPK-3"})
    password = str(body.get("passPhrase") or "")
    body["passPhrase"] = ""
    email = str(body.get("mailAddress") or "").strip().lower()
    if not email or "@" not in email:
        return Response.json({"errorMessage": "SPK-3"})
    role = str(body.get("role") or "").strip()
    responsibility = str(body.get("responsibility") or "").strip()
    if role not in VALID_ROLES or (responsibility and responsibility not in VALID_RESPONSIBILITIES):
        return Response.json({"errorMessage": "SPK-3"})
    change_passphrase = _bool(request.query.get("changePassphrase"))
    try:
        with connect() as db:
            existing = db.execute(USER_SELECT + " WHERE trim(lower(e_mail))=%s", (email,)).fetchall()
            if len(existing) != 1:
                return Response.json({"errorMessage": "SPK-3"})
            active_admins = db.execute(
                "SELECT count(*) AS count FROM \"wgr_sp_kontrolleur\" WHERE aktiv=true AND rolle='administrator'"
            ).fetchone()["count"]
            old = existing[0]
            if old["role"] == "administrator" and active_admins == 1:
                if body.get("role") != "administrator" or not _bool(body.get("active")):
                    return Response.json({"errorMessage": "SPK-3"})
            affected = db.execute(
                '''UPDATE "wgr_sp_kontrolleur"
                   SET nachname=%s, vorname=%s, rolle=%s, zustaendigkeit=%s, aktiv=%s, is_new=%s
                   WHERE trim(lower(e_mail))=%s''',
                (body.get("lastName") or "", body.get("firstName") or "", role,
                 responsibility or None,
                 _bool(body.get("active")), _bool(body.get("isNew")), email),
            ).rowcount
            password_affected = 0
            if change_passphrase:
                password = password.strip()
                if len(password) < 8:
                    return Response.json({"errorMessage": "SPK-9"})
                password_affected = db.execute(
                    "UPDATE \"wgr_sp_kontrolleur\" SET pwd=%s WHERE trim(lower(e_mail))=%s",
                    (hash_passphrase(password, email), email),
                ).rowcount
            if affected == 1 and (not change_passphrase or password_affected == 1):
                body.setdefault("errorMessage", "")
                return Response.json(body)
    except Exception:
        pass
    return Response.json({"errorMessage": "SPK-3"})


def delete_user(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    email = request.query.get("email", "").strip().lower()
    if not email:
        return Response.json({"errorMessage": "SPK-3"})
    with connect() as db:
        users = db.execute(USER_SELECT + " WHERE trim(lower(e_mail))=%s", (email,)).fetchall()
        if len(users) != 1:
            return Response.json({"errorMessage": "SPK-3"})
        count = db.execute(
            "SELECT count(*) AS count FROM \"wgr_sp_kontrolleur\" WHERE aktiv=true AND rolle='administrator'"
        ).fetchone()["count"]
        if users[0]["role"] == "administrator" and count == 1:
            return Response.json({"errorMessage": "SPK-3"})
        if db.execute("UPDATE \"wgr_sp_kontrolleur\" SET aktiv=false WHERE trim(lower(e_mail))=%s", (email,)).rowcount == 1:
            return Response(b"", 200, "application/json; charset=utf-8")
    return Response.json({"errorMessage": "SPK-3"})


def inspection_types(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    return Response.json([f"{row['value']} ({row['short_value']})" for row in rows])


def renovation_types(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        rows = db.execute('SELECT value FROM "wgr_sp_sanierungsart_tbd"').fetchall()
    return Response.json([row["value"] for row in rows])


def _suspended(row: Mapping[str, Any]) -> bool:
    today = date.today()
    start = _date_value(row.get("suspend_from"))
    end = _date_value(row.get("suspend_to"))
    start_date = start.date() if isinstance(start, datetime) else start
    end_date = end.date() if isinstance(end, datetime) else end
    if start_date is None and end_date is None:
        return False
    if start_date is None:
        return today <= end_date
    if end_date is None:
        return today >= start_date
    return start_date <= today <= end_date


def only_names(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    inspection_type = request.query.get("inspectiontype", request.query.get("inspectionType", ""))
    params: tuple[Any, ...] = ()
    sql = '''SELECT DISTINCT ON (sp.name)
        sp.name, insp.datum_inspektion AS date_of_last_inspection,
        sp.inspektion_aussetzen_von AS suspend_from,
        sp.inspektion_aussetzen_bis AS suspend_to,
        (SELECT count(*) > 0 FROM "wgr_sp_insp_mangel" mangel
         JOIN "gr_v_spielgeraete" geraete ON mangel.fid_spielgeraet=geraete.fid
         WHERE geraete.fid_spielplatz=sp.fid AND mangel.fid_erledigung IS NULL) AS has_open
        FROM "wgr_sp_spielplatz" sp
        LEFT JOIN "wgr_sp_inspektion" insp ON insp.fid_spielplatz=sp.fid
        ORDER BY sp.name, insp.datum_inspektion DESC'''
    if user and inspection_type and inspection_type != "Keine Inspektion":
        base_type = inspection_type[:-5]
        sql = '''SELECT DISTINCT ON (sp.name)
            sp.name, insp.datum_inspektion AS date_of_last_inspection,
            sp.inspektion_aussetzen_von AS suspend_from,
            sp.inspektion_aussetzen_bis AS suspend_to, false AS has_open
            FROM "wgr_sp_spielplatz" sp
            JOIN "wgr_sp_inspart_kontr" ikt ON sp.fid=ikt.fid_spielplatz
            JOIN "wgr_sp_kontrolleur" kt ON kt.fid=ikt.fid_kontrolleur
            JOIN "wgr_sp_inspektionsart_tbd" ina ON ina.id=ikt.id_inspektionsart
            LEFT JOIN "wgr_sp_inspektion" insp ON insp.fid_spielplatz=sp.fid
            WHERE trim(lower(kt.e_mail))=%s AND ina.value=%s
            ORDER BY sp.name, insp.datum_inspektion DESC'''
        params = (user["mailAddress"], base_type)
    with connect() as db:
        rows = db.execute(sql, params).fetchall()
    result = []
    for row in rows:
        suspended = _suspended(row)
        if inspection_type != "Keine Inspektion" and suspended:
            continue
        result.append({
            "id": 0, "name": row["name"], "address": "",
            "dateOfLastInspection": row["date_of_last_inspection"] or DOTNET_MIN_DATE,
            "suspendInspectionFrom": row["suspend_from"], "suspendInspectionTo": row["suspend_to"],
            "inspectionSuspended": suspended, "hasOpenDeviceDefects": bool(row["has_open"]),
            "playdevices": [], "defectPriorityOptions": [], "inspectionTypeOptions": [],
            "renovationTypeOptions": [], "defectsResponsibleBodyOptions": [],
            "documentsOfAcceptanceFids": [], "certificateDocumentsFids": [],
        })
    return Response.json(result)


def _public_feature(row: Mapping[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    row = row or {}
    coordinates = [] if row.get("x") is None else [row["x"], row["y"]]
    return {
        "type": "Feature",
        "properties": {
            "uuid": str(row.get("uuid") or ""), "nummer": row.get("number") if row.get("number") is not None else -1,
            "name": row.get("name") or "", "streetName": row.get("street_name") or "", "houseNo": row.get("house_no") or "",
        },
        "geometry": {"type": "Point", "coordinates": coordinates},
        "errorMessage": error,
    }


def public_playgrounds(request: Request) -> Response:
    try:
        with connect() as db:
            rows = db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y FROM "wgr_sp_spielplatz"'''
            ).fetchall()
        return Response.json([_public_feature(row) for row in rows])
    except Exception:
        return Response.json([_public_feature(error="Unknown critical error.")])


def public_playground(request: Request) -> Response:
    uuid = request.params.get("uuid", "").strip().lower()
    if not uuid:
        return Response.json(_public_feature(error="No valid UUID provided."))
    try:
        with connect() as db:
            row = db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y
                FROM "wgr_sp_spielplatz" WHERE uuid::text=%s''', (uuid,)).fetchone()
        if not row:
            return Response.json(_public_feature({"uuid": uuid}, "No playground found for given UUID."))
        return Response.json(_public_feature(row))
    except Exception:
        return Response.json(_public_feature({"uuid": uuid}, "Unknown critical error."))


def get_map_image(request: Request) -> Response:
    x = float(request.query.get("x", "0") or 0)
    y = float(request.query.get("y", "0") or 0)
    if x == 0 or y == 0:
        return Response.json("")
    endpoint = settings.wms_url.strip()
    if not endpoint.lower().startswith(("http://", "https://")):
        endpoint = "http://" + endpoint
    if not endpoint.rstrip("/").endswith("Spielplatzkarte"):
        endpoint = endpoint.rstrip("/") + "/Spielplatzkarte"
    url = endpoint + "?LAYERS=AV_UEP_Landeskarten,Spielplatz&VERSION=1.1.1&DPI=96&TRANSPARENT=TRUE&FORMAT=image%2Fpng&" \
        "SERVICE=WMS&REQUEST=GetMap&STYLES=&SRS=EPSG%3A2056&" \
        f"BBOX={x-10},{y-5},{x+10},{y+5}&WIDTH=800&HEIGHT=400"
    try:
        response = urlopen(url, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        return Response.json(base64.b64encode(response.read()).decode("ascii"))


def _user_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = db.execute(
        'SELECT vorname AS first_name, nachname AS last_name FROM "wgr_sp_kontrolleur" WHERE fid=%s',
        (fid,),
    ).fetchone()
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _record_assignment_change(
    db: Connection, defect_tid: int, changed_by: Mapping[str, Any], previous_fid: Any, new_fid: Any
) -> None:
    previous = int(previous_fid) if previous_fid else None
    new = int(new_fid) if new_fid else None
    if previous == new:
        return
    changed_by_name = f"{changed_by.get('firstName') or ''} {changed_by.get('lastName') or ''}".strip()
    db.execute(
        '''INSERT INTO "wgr_sp_mangel_zuweisung_hist"
            (tid_mangel, geaendert_am, geaendert_durch_fid, geaendert_durch_name,
             vorher_fid, vorher_name, nachher_fid, nachher_name)
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s)''',
        (defect_tid, changed_by.get("fid"), changed_by_name or None,
         previous, _user_name(db, previous) or None, new, _user_name(db, new) or None),
    )


def _assignment_history(db: Connection, defect_tid: int) -> list[dict[str, Any]]:
    rows = db.execute(
        '''SELECT id, geaendert_am AS changed_at, geaendert_durch_fid AS changed_by_fid,
            geaendert_durch_name AS changed_by_name, vorher_fid AS previous_fid,
            vorher_name AS previous_name, nachher_fid AS new_fid, nachher_name AS new_name
            FROM "wgr_sp_mangel_zuweisung_hist"
            WHERE tid_mangel=%s ORDER BY geaendert_am DESC, id DESC''',
        (defect_tid,),
    ).fetchall()
    return [{
        "id": row.get("id"),
        "changedAt": row.get("changed_at"),
        "changedByFid": row.get("changed_by_fid") or -1,
        "changedByName": row.get("changed_by_name") or "",
        "previousUserFid": row.get("previous_fid") or -1,
        "previousUserName": row.get("previous_name") or "",
        "newUserFid": row.get("new_fid") or -1,
        "newUserName": row.get("new_name") or "",
    } for row in rows]


def _defect_creator_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = db.execute(
        'SELECT vorname AS first_name, nachname AS last_name FROM "wgr_sp_kontrolleur" WHERE fid=%s',
        (fid,),
    ).fetchone()
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _defect_dict(db: Connection, row: Mapping[str, Any], pictures: bool = True) -> dict[str, Any]:
    before: list[int] = []
    after: list[int] = []
    if pictures:
        rows = db.execute(
            'SELECT tid, zeitpunkt AS after_fixing FROM "wgr_sp_insp_mangel_foto" WHERE tid_maengel=%s',
            (row["tid"],),
        ).fetchall()
        for picture in rows:
            (after if picture["after_fixing"] else before).append(picture["tid"])
    return {
        "tid": row["tid"], "playdeviceFid": row.get("playdevice_fid") or 0,
        "priority": row.get("priority") if row.get("priority") is not None else -1,
        "defectPicsTids": before, "defectPicsAfterFixingTids": after,
        "defectDescription": row.get("description") or "", "dateCreation": row.get("date_creation"),
        "dateDone": row.get("date_done"), "done": row.get("done_by") is not None,
        "doneByFid": row.get("done_by") or -1,
        "doneByName": _defect_creator_name(db, row.get("done_by")),
        "defectComment": row.get("comment") or "",
        "defectsResponsibleBodyId": row.get("responsible_body_id") or -1,
        "responsibleUserFid": row.get("responsible_user_fid") or -1,
        "assignmentStatus": row.get("assignment_status") or "",
        "dateAssignmentCreated": row.get("assignment_created"),
        "dateAssignmentAccepted": row.get("assignment_accepted"),
        "dateAssignmentRejected": row.get("assignment_rejected"),
        "assignmentComment": row.get("assignment_comment") or "",
        "infoMailSentAt": row.get("info_mail_sent_at"),
        "infoMailRecipientName": row.get("info_mail_recipient_name") or "",
        "createdByFid": row.get("created_by_fid") or -1,
        "createdByName": _defect_creator_name(db, row.get("created_by_fid")),
        "assignmentHistory": _assignment_history(db, int(row["tid"])),
        "errorMessage": "",
    }


def _report_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tid": row.get("tid", -1), "inspectionType": row.get("inspection_type") or "",
        "dateOfService": row.get("inspection_date"), "inspector": row.get("inspector") or "",
        "inspectionText": row.get("inspection_text") or "", "inspectionDone": bool(row.get("inspection_done")),
        "inspectionComment": row.get("inspection_comment") or "", "maintenanceText": row.get("maintenance_text") or "",
        "maintenanceDone": bool(row.get("maintenance_done")), "maintenanceComment": row.get("maintenance_comment") or "",
        "fallProtectionType": row.get("fall_protection") or "", "playdeviceFid": row.get("playdevice_fid") or 0,
        "playdeviceDetailFid": row.get("playdevice_detail_fid") or 0,
        "tidInspection": row.get("inspection_tid") if row.get("inspection_tid") is not None else -1,
    }


def _criterion_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "realm": row.get("realm") or "", "designation": "", "check": row.get("check_text") or "",
        "checkShortText": row.get("check_short_text") or "", "maintenance": row.get("maintenance") or "",
        "beforeOpening": False, "weekly": False, "monthly": False, "yearly": False,
        "inspectionType": row.get("inspection_type") or "",
        "currentInspectionReport": {
            "tid": 0, "inspectionType": "", "inspector": "", "inspectionText": "", "inspectionDone": False,
            "inspectionComment": "", "maintenanceText": "", "maintenanceDone": False,
            "maintenanceComment": "", "fallProtectionType": "", "playdeviceFid": 0, "playdeviceDetailFid": 0,
        },
    }


def _playdevice_rows(db: Connection, playground_id: int) -> list[Mapping[str, Any]]:
    return db.execute('''SELECT spg.fid, spg.bemerkungen AS comment,
        ST_X(spg.geom) AS x, ST_Y(spg.geom) AS y,
        gart.short_value AS type_name, gart.value AS type_description,
        spg.norm AS standard, lief.name AS supplier,
        spg.empfohlenes_sanierungsjahr AS recommended_year,
        spg.bemerkung_empf_sanierung AS renovation_comment,
        spg.nicht_zu_pruefen AS not_to_be_checked,
        spg.nicht_pruefbar AS cannot_be_checked,
        spg.grund_nicht_pruefbar AS cannot_be_checked_reason,
        spg.bau_dat AS construction_date, spg.id_sanierungsart AS renovation_type,
        EXISTS (
            SELECT 1 FROM "wgr_sp_insp_mangel" mangel
            WHERE mangel.fid_spielgeraet=spg.fid AND mangel.fid_erledigung IS NULL
        ) AS has_open_defects
        FROM "gr_v_spielgeraete" spg
        LEFT JOIN "wgr_sp_spielgeraeteart_tbd" gart ON spg.id_geraeteart=gart.id
        LEFT JOIN "wgr_sp_lieferant" lief ON spg.id_lieferant=lief.fid
        WHERE spg.fid_spielplatz=%s''', (playground_id,)).fetchall()


def _criteria(db: Connection, view: str, type_column: str, fid: int, inspection_type: str) -> list[dict[str, Any]]:
    # View and column names are fixed constants originating in the C# service.
    sql = f'''SELECT bereich AS realm, pruefung AS check_text, wartung AS maintenance,
        {type_column} AS inspection_type, pruefung_kurztext AS check_short_text
        FROM "{view}" WHERE fid_spielgeraet=%s AND {type_column}=%s'''
    return [_criterion_dict(row) for row in db.execute(sql, (fid, inspection_type)).fetchall()]


def _inspection_history(db: Connection, fid: int, inspection_types: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    last: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    for inspection_type in inspection_types:
        rows = db.execute('''SELECT tid, inspektionsart AS inspection_type,
            datum_inspektion AS inspection_date, kontrolleur AS inspector,
            pruefung_text AS inspection_text, pruefung_erledigt AS inspection_done,
            pruefung_kommentar AS inspection_comment, wartung_text AS maintenance_text,
            wartung_erledigung AS maintenance_done, wartung_kommentar AS maintenance_comment,
            fallschutz AS fall_protection, tid_inspektion AS inspection_tid,
            fid_spielgeraet AS playdevice_fid, fid_geraet_detail AS playdevice_detail_fid
            FROM "wgr_sp_insp_bericht"
            WHERE tid_inspektion IN (
                SELECT tid_inspektion FROM "wgr_sp_insp_bericht"
                WHERE fid_spielgeraet=%s AND inspektionsart=%s
                GROUP BY tid_inspektion, datum_inspektion
                ORDER BY datum_inspektion DESC LIMIT 2)
              AND fid_spielgeraet=%s AND inspektionsart=%s
            ORDER BY datum_inspektion, tid_inspektion DESC''',
            (fid, inspection_type, fid, inspection_type),
        ).fetchall()
        if not rows:
            continue
        first_tid = rows[0].get("inspection_tid")
        previous.append(_report_dict(rows[0]))
        for row in rows[1:]:
            (previous if row.get("inspection_tid") == first_tid else last).append(_report_dict(row))
    return last, previous


def _playdevice(db: Connection, row: Mapping[str, Any], inspection_type: str, with_defects: bool, with_inspections: bool) -> dict[str, Any]:
    base_type = inspection_type[:-5] if inspection_type and len(inspection_type) > 5 else inspection_type
    general: list[dict[str, Any]] = []
    main: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    last: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    if with_inspections:
        general = _criteria(db, "wgr_v_sp_ger_insp_krit", "inspektionsart", row["fid"], base_type)
        main = _criteria(db, "wgr_v_sp_hfall_insp_krit", "insektionsart", row["fid"], base_type)
        secondary = _criteria(db, "wgr_v_sp_nfall_insp_krit", "insektionsart", row["fid"], base_type)
        types = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
        last, previous = _inspection_history(db, row["fid"], [f"{x['value']} ({x['short_value']})" for x in types])
    defects = None
    if with_defects:
        defects = [_defect_dict(db, item, False) for item in db.execute(
            DEFECT_SELECT + " WHERE fid_spielgeraet=%s AND datum_erledigung IS NULL", (row["fid"],)
        ).fetchall()]
    return {
        "type": "Feature",
        "properties": {
            "fid": row["fid"], "supplier": row.get("supplier") or "", "material": "", "lebensdauer": 0,
            "comment": row.get("comment") or "",
            "type": {"name": row.get("type_name") or "", "description": row.get("type_description") or "", "standard": row.get("standard") or ""},
            "dateOfService": DOTNET_MIN_DATE, "constructionDate": row.get("construction_date") or DOTNET_MIN_DATE,
            "generalInspectionCriteria": general, "mainFallProtectionInspectionCriteria": main,
            "secondaryFallProtectionInspectionCriteria": secondary,
            "recommendedYearOfRenovation": row.get("recommended_year") or 0,
            "renovationType": row.get("renovation_type") or 0,
            "commentRecommendedYearOfRenovation": row.get("renovation_comment") or "",
            "notToBeChecked": bool(row.get("not_to_be_checked")), "cannotBeChecked": bool(row.get("cannot_be_checked")),
            "cannotBeCheckedReason": row.get("cannot_be_checked_reason") or "",
            "hasOpenDefects": bool(row.get("has_open_defects")), "defects": defects,
            "lastInspectionReports": last, "nextToLastInspectionReports": previous,
            "pictureBase64String": "", "mapImageBase64String": "",
        },
        "geometry": {"type": "Point", "coordinates": [row.get("x"), row.get("y")]},
    }


def _playground_result(db: Connection, row: Mapping[str, Any], inspection_type: str, with_defects: bool, with_inspections: bool) -> dict[str, Any]:
    devices = [
        _playdevice(db, item, inspection_type, with_defects, with_inspections)
        for item in _playdevice_rows(db, row["id"])
        if not item.get("not_to_be_checked")
    ]
    priorities = db.execute('SELECT id, short_value, value FROM "wgr_sp_dringlichkeit_tbd"').fetchall()
    priority_options = []
    for item in priorities:
        short = (item.get("short_value") or "").strip()
        long = (item.get("value") or "").strip()
        final = short + (f" ({long})" if short and long else long)
        if final:
            priority_options.append(final)
    type_rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    type_options = [f"{item['value']} ({item['short_value']})" for item in type_rows]
    renovations = [{"id": item["id"], "value": item["value"]} for item in db.execute(
        'SELECT id, value FROM "wgr_sp_sanierungsart_tbd"'
    ).fetchall()]
    if settings.compatibility_bugs and renovations:
        renovations = [dict(renovations[-1]) for _ in renovations]
    bodies = [{"id": item["id"], "value": item["value"]} for item in db.execute(
        'SELECT id, value FROM "wgr_sp_zust_mangelbeheb_tbd"'
    ).fetchall()]
    acceptance_rows = db.execute(
        'SELECT fid, substring(abnahmedokument from greatest(octet_length(abnahmedokument)-1023,1)) AS meta_tail '
        'FROM "wgr_sp_abnahmen" WHERE fid_spielplatz=%s AND abnahmedokument IS NOT NULL ORDER BY fid', (row["id"],)
    ).fetchall()
    certificate_rows = db.execute(
        'SELECT fid, substring(zertifikatsdokument from greatest(octet_length(zertifikatsdokument)-1023,1)) AS meta_tail '
        'FROM "wgr_sp_zertifikat" WHERE fid_spielplatz=%s AND zertifikatsdokument IS NOT NULL ORDER BY fid', (row["id"],)
    ).fetchall()
    acceptance = [item["fid"] for item in acceptance_rows]
    certificates = [item["fid"] for item in certificate_rows]
    acceptance_documents = [
        {"fid": item["fid"], "name": _document_name_from_tail(item.get("meta_tail"), str(item["fid"]))}
        for item in acceptance_rows
    ]
    certificate_documents = [
        {"fid": item["fid"], "name": _document_name_from_tail(item.get("meta_tail"), str(item["fid"]))}
        for item in certificate_rows
    ]
    return {
        "id": row["id"], "name": row.get("name") or "", "address": row.get("address") or "",
        "dateOfLastInspection": row.get("date_of_last_inspection") or DOTNET_MIN_DATE,
        "suspendInspectionFrom": row.get("suspend_from"), "suspendInspectionTo": row.get("suspend_to"),
        "inspectionSuspended": _suspended(row), "hasOpenDeviceDefects": False,
        "playdevices": devices, "defectPriorityOptions": priority_options,
        "inspectionTypeOptions": type_options, "renovationTypeOptions": renovations,
        "defectsResponsibleBodyOptions": bodies, "chosenTypeOfInspection": "",
        "documentsOfAcceptanceFids": acceptance, "certificateDocumentsFids": certificates,
        "documentsOfAcceptance": acceptance_documents, "certificateDocuments": certificate_documents,
    }


def playground_by_name_data(query: Mapping[str, str]) -> dict[str, Any]:
    """Return the established detail payload independently of the HTTP framework."""
    with connect() as db:
        row = db.execute('''SELECT sp.fid AS id, sp.name,
            sp.inspektion_aussetzen_von AS suspend_from,
            sp.inspektion_aussetzen_bis AS suspend_to,
            insp.datum_inspektion AS date_of_last_inspection, '' AS address
            FROM "wgr_sp_spielplatz" sp
            LEFT JOIN (SELECT fid_spielplatz, MAX(datum_inspektion) AS max_datum
                       FROM "wgr_sp_inspektion" GROUP BY fid_spielplatz) insp_max
              ON insp_max.fid_spielplatz=sp.fid
            LEFT JOIN "wgr_sp_inspektion" insp
              ON insp.fid_spielplatz=insp_max.fid_spielplatz AND insp.datum_inspektion=insp_max.max_datum
            WHERE sp.name=%s LIMIT 1''', (query.get("name", ""),)).fetchone()
        if not row:
            raise LookupError("Sequence contains no elements")
        inspection = query.get("inspectiontype", query.get("inspectionType", ""))
        result = _playground_result(db, row, inspection, _bool(query.get("withdefects")), _bool(query.get("withinspections")))
    return result


def get_playground_by_name(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    return Response.json(playground_by_name_data(request.query))

def invalid_playground_id(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    invalid_id = request.params.get("invalid_id", "")
    return Response.json({
        "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
        "title": "One or more validation errors occurred.",
        "status": 400,
        "errors": {"id": [f"The value '{invalid_id}' is not valid."]},
    }, 400)


def get_playground_by_id(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    if settings.compatibility_bugs:
        return Response.text("Index was outside the bounds of the array.", 500)
    with connect() as db:
        row = db.execute('''SELECT fid AS id, name,
            inspektion_aussetzen_von AS suspend_from, inspektion_aussetzen_bis AS suspend_to,
            NULL::date AS date_of_last_inspection, '' AS address
            FROM "wgr_sp_spielplatz" WHERE fid=%s''', (int(request.params["id"]),)).fetchone()
        result = _playground_result(db, row, request.query.get("inspectiontype", ""),
            _bool(request.query.get("withdefects")), _bool(request.query.get("withinspections"))) if row else None
    return Response.json(result)


def get_playground_by_device(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    fid = int(request.params["fid"])
    if fid <= 0:
        return Response.json({"id": 0, "name": "", "address": "", "playdevices": []})
    with connect() as db:
        row = db.execute('''SELECT sp.fid AS id, sp.name,
            TRIM(CONCAT(COALESCE(sp.strassenname,''), ' ', COALESCE(sp.hausnummer,''))) AS address,
            sp.inspektion_aussetzen_von AS suspend_from, sp.inspektion_aussetzen_bis AS suspend_to,
            NULL::date AS date_of_last_inspection
            FROM "gr_v_spielgeraete" geraet JOIN "wgr_sp_spielplatz" sp ON sp.fid=geraet.fid_spielplatz
            WHERE geraet.fid=%s''', (fid,)).fetchone()
        if not row:
            return Response.json({"id": 0, "name": "", "address": "", "playdevices": []})
        devices = [_playdevice(db, item, "", False, False) for item in _playdevice_rows(db, row["id"]) if item["fid"] == fid]
    return Response.json({
        "id": row["id"], "name": row.get("name") or "", "address": row.get("address") or "",
        "dateOfLastInspection": DOTNET_MIN_DATE, "suspendInspectionFrom": None, "suspendInspectionTo": None,
        "inspectionSuspended": False, "hasOpenDeviceDefects": False, "playdevices": devices,
        "defectPriorityOptions": [], "inspectionTypeOptions": [], "renovationTypeOptions": [],
        "defectsResponsibleBodyOptions": [], "chosenTypeOfInspection": "",
        "documentsOfAcceptanceFids": [], "certificateDocumentsFids": [],
    })


def save_playdevice(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    body = request.json()
    props = (body or {}).get("properties", {})
    if not props:
        return Response.json({"errorMessage": "SPK-5"})
    try:
        with connect() as db:
            db.execute('''UPDATE "gr_v_spielgeraete" SET
                empfohlenes_sanierungsjahr=%s, id_sanierungsart=%s,
                bemerkung_empf_sanierung=%s, nicht_pruefbar=%s,
                grund_nicht_pruefbar=%s WHERE fid=%s''',
                (props.get("recommendedYearOfRenovation") if int(props.get("recommendedYearOfRenovation") or 0) > 0 else None,
                 props.get("renovationType") if int(props.get("renovationType") or 0) != 0 else None,
                 props.get("commentRecommendedYearOfRenovation") or None, _bool(props.get("cannotBeChecked")),
                 props.get("cannotBeCheckedReason") or "", int(props.get("fid") or 0)),
            )
        return Response.json({"errorMessage": ""})
    except Exception:
        return Response.json({"errorMessage": "SPK-3"})


def get_defect_overview(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        rows = db.execute('''SELECT
            mangel.tid, mangel.fid_spielgeraet AS playdevice_fid,
            spielplatz.name AS playground_name,
            COALESCE(geraeteart.value, geraeteart.short_value, '') AS playdevice_type,
            geraet.norm AS standard,
            mangel.id_dringlichkeit AS priority,
            mangel.beschrieb AS description,
            mangel.bemerkunng AS comment,
            mangel.datum AS date_creation,
            mangel.datum_erledigung AS date_done,
            mangel.fid_erledigung AS done_by,
            mangel.id_zustaendig_behebung AS responsible_body_id,
            mangel.fid_zustaendig_kontrolleur AS responsible_user_fid,
            TRIM(CONCAT(COALESCE(kontrolleur.vorname, ''), ' ', COALESCE(kontrolleur.nachname, ''))) AS responsible_user_name,
            (
                mangel.fid_erledigung IS NULL
                AND mangel.id_dringlichkeit = 1
                AND mangel.auftrag_status = 'zugewiesen'
                AND mangel.datum_auftrag_zugewiesen IS NOT NULL
                AND mangel.datum_auftrag_angenommen IS NULL
                AND mangel.datum_auftrag_abgelehnt IS NULL
                AND mangel.datum_auftrag_zugewiesen <= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) AS assignment_overdue
            FROM "wgr_sp_insp_mangel" mangel
            LEFT JOIN "gr_v_spielgeraete" geraet ON geraet.fid=mangel.fid_spielgeraet
            LEFT JOIN "wgr_sp_spielplatz" spielplatz ON spielplatz.fid=geraet.fid_spielplatz
            LEFT JOIN "wgr_sp_spielgeraeteart_tbd" geraeteart ON geraeteart.id=geraet.id_geraeteart
            LEFT JOIN "wgr_sp_kontrolleur" kontrolleur ON kontrolleur.fid=mangel.fid_zustaendig_kontrolleur
            ORDER BY (mangel.fid_erledigung IS NOT NULL), mangel.datum, spielplatz.name, geraeteart.value
        ''').fetchall()
    result = []
    for row in rows:
        result.append({
            "tid": row["tid"],
            "playdeviceFid": row.get("playdevice_fid") or 0,
            "playgroundName": row.get("playground_name") or "",
            "playdeviceType": row.get("playdevice_type") or "",
            "standard": row.get("standard") or "",
            "priority": row.get("priority") if row.get("priority") is not None else -1,
            "defectDescription": row.get("description") or "",
            "defectComment": row.get("comment") or "",
            "dateCreation": row.get("date_creation"),
            "dateDone": row.get("date_done"),
            "done": row.get("done_by") is not None,
            "defectsResponsibleBodyId": row.get("responsible_body_id") or -1,
            "responsibleUserFid": row.get("responsible_user_fid") or -1,
            "responsibleUserName": row.get("responsible_user_name") or "",
            "assignmentOverdue": bool(row.get("assignment_overdue")),
        })
    return Response.json(result)


def get_defect(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        row = db.execute(DEFECT_SELECT + " WHERE tid=%s", (int(request.query.get("tid", "0")),)).fetchone()
        result = _defect_dict(db, row) if row else None
    return Response.json(result)


def _priority_two_fields_complete(body: Mapping[str, Any]) -> bool:
    try:
        priority = int(body.get("priority") or 0)
        responsible_body = int(body.get("defectsResponsibleBodyId") or -1)
        responsible_user = int(body.get("responsibleUserFid") or -1)
    except (TypeError, ValueError):
        return False
    return priority != 2 or (responsible_body > 0 and responsible_user > 0)


def create_defect(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    body = request.json() or {}
    body.pop("done", None)
    if not body.get("defectDescription"):
        return Response.json(body)
    if not _priority_two_fields_complete(body):
        body["errorMessage"] = "SPK-10"
        return Response.json(body)
    try:
        responsible = int(body.get("responsibleUserFid") or -1)
        date_done = date.today() if body.get("dateDone") is not None else None
        with connect() as db:
            db.execute('LOCK TABLE "wgr_sp_insp_mangel" IN EXCLUSIVE MODE')
            row = db.execute('''INSERT INTO "wgr_sp_insp_mangel"
                (tid, fid_spielgeraet, datum, id_dringlichkeit, beschrieb, bemerkunng,
                 datum_erledigung, fid_erledigung, id_zustaendig_behebung,
                 fid_zustaendig_kontrolleur, auftrag_status, datum_auftrag_zugewiesen, bemerkung_auftrag,
                 fid_erfassung)
                VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_insp_mangel"),
                 %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING tid''',
                (body.get("playdeviceFid"), body.get("priority"), body.get("defectDescription") or "",
                 body.get("defectComment") or "", date_done, user["fid"] if date_done else None,
                 body.get("defectsResponsibleBodyId") if int(body.get("defectsResponsibleBodyId") or -1) > 0 else None,
                 responsible if responsible > 0 else None, "zugewiesen" if responsible > 0 else None,
                 datetime.now() if responsible > 0 else None, (body.get("assignmentComment") or "").strip() or None,
                 user["fid"]),
            ).fetchone()
            if responsible > 0:
                _record_assignment_change(db, int(row["tid"]), user, None, responsible)
            body["assignmentHistory"] = _assignment_history(db, int(row["tid"]))
        body["tid"] = row["tid"]
        body.setdefault("errorMessage", "")
    except Exception:
        body["errorMessage"] = "SPK-3"
    return Response.json(body)


def update_defect(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    body = request.json() or {}
    if not body:
        return Response.json({"errorMessage": "SPK-4"})
    if not _priority_two_fields_complete(body):
        return Response.json({"errorMessage": "SPK-10"})
    try:
        responsible = int(body.get("responsibleUserFid") or -1)
        date_done = _date_value(body.get("dateDone"))
        with connect() as db:
            current = db.execute(
                'SELECT fid_zustaendig_kontrolleur AS responsible_user_fid FROM "wgr_sp_insp_mangel" WHERE tid=%s',
                (body.get("tid"),),
            ).fetchone()
            if not current:
                return Response.json({"errorMessage": "SPK-3"})
            new_responsible = responsible if responsible > 0 else None
            assignment_changed = current.get("responsible_user_fid") != new_responsible
            assignment_status_value = (
                "zugewiesen" if new_responsible and assignment_changed
                else (body.get("assignmentStatus") or "zugewiesen") if new_responsible else None
            )
            assignment_created_value = (
                datetime.now() if new_responsible and assignment_changed
                else (_date_value(body.get("dateAssignmentCreated")) or datetime.now()) if new_responsible else None
            )
            assignment_comment_value = (
                None if assignment_changed else (body.get("assignmentComment") or "").strip() or None
            )
            db.execute('''UPDATE "wgr_sp_insp_mangel" SET
                id_dringlichkeit=%s, beschrieb=%s, bemerkunng=%s, datum_erledigung=%s,
                id_zustaendig_behebung=%s, fid_zustaendig_kontrolleur=%s,
                auftrag_status=%s, datum_auftrag_zugewiesen=%s, bemerkung_auftrag=%s,
                datum_auftrag_angenommen=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE datum_auftrag_angenommen END,
                datum_auftrag_abgelehnt=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE datum_auftrag_abgelehnt END,
                infomail_gesendet_am=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE infomail_gesendet_am END,
                infomail_empfaenger=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE infomail_empfaenger END,
                fid_erledigung=%s WHERE tid=%s''',
                (body.get("priority"), body.get("defectDescription") or "", body.get("defectComment") or "", date_done,
                 body.get("defectsResponsibleBodyId") if int(body.get("defectsResponsibleBodyId") or -1) > 0 else None,
                 new_responsible, assignment_status_value, assignment_created_value, assignment_comment_value,
                 new_responsible, new_responsible, new_responsible, new_responsible,
                 user["fid"] if date_done else None, body.get("tid")),
            )
            _record_assignment_change(
                db, int(body.get("tid")), user, current.get("responsible_user_fid"), new_responsible,
            )
        return Response.json({"errorMessage": ""})
    except Exception:
        return Response.json({"errorMessage": "SPK-3"})


def assignment_status(request: Request, accepted: bool) -> Response:
    user, error = require_user(request)
    if error:
        return error
    body = request.json() or {}
    comment = (body.get("assignmentComment") or "").strip() or None
    with connect() as db:
        assignment_matches_user = '''(
            mangel.fid_zustaendig_kontrolleur=%s OR EXISTS (
                SELECT 1 FROM "wgr_sp_kontrolleur" kontrolleur
                WHERE kontrolleur.fid=mangel.fid_zustaendig_kontrolleur
                AND trim(lower(kontrolleur.e_mail))=%s
            )
        )'''
        params = (comment, int(request.params["tid"]), user["fid"], user["mailAddress"])
        if accepted:
            cursor = db.execute(f'''UPDATE "wgr_sp_insp_mangel" AS mangel SET auftrag_status='angenommen',
                datum_auftrag_angenommen=CURRENT_TIMESTAMP, datum_auftrag_abgelehnt=NULL,
                bemerkung_auftrag=%s WHERE tid=%s AND {assignment_matches_user}''', params)
        else:
            cursor = db.execute(f'''UPDATE "wgr_sp_insp_mangel" AS mangel SET auftrag_status='abgelehnt',
                datum_auftrag_abgelehnt=CURRENT_TIMESTAMP, datum_auftrag_angenommen=NULL, bemerkung_auftrag=%s
                WHERE tid=%s AND {assignment_matches_user}''', params)
    return Response.json({"errorMessage": "" if cursor.rowcount == 1 else "SPK-3"})


def send_info_mail(request: Request) -> Response:
    # Send a defect notification using server-side recipient data.
    user, error = require_user(request)
    if error:
        return error
    tid = int(request.params["tid"])
    from .mail_service import MailAttachment, compose_defect_mail, deliver, MailConfigurationError

    try:
        with connect() as db:
            row = db.execute(DEFECT_SELECT + " WHERE tid=%s", (tid,)).fetchone()
            if not row:
                return Response.text("Mangel nicht gefunden.", 404)
            recipient = db.execute('''SELECT fid, TRIM(CONCAT(vorname, ' ', nachname)) AS name,
                TRIM(LOWER(e_mail)) AS email, aktiv AS active
                FROM "wgr_sp_kontrolleur" WHERE fid=%s''', (row.get("responsible_user_fid"),)).fetchone()
            if not recipient or not recipient.get("active") or not recipient.get("email") or not _valid_mail_address(recipient["email"]):
                return Response.text("Die zuständige Person hat keine gültige aktive E-Mail-Adresse.", 400)
            device_row = db.execute('''SELECT sp.name AS playground_name,
                TRIM(CONCAT(COALESCE(sp.strassenname,''), ' ', COALESCE(sp.hausnummer,''))) AS address,
                gart.value AS device_type, lief.name AS supplier, geraet.bau_dat AS construction_date,
                geraet.bemerkungen AS device_comment
                FROM "gr_v_spielgeraete" geraet
                JOIN "wgr_sp_spielplatz" sp ON sp.fid=geraet.fid_spielplatz
                LEFT JOIN "wgr_sp_spielgeraeteart_tbd" gart ON geraet.id_geraeteart=gart.id
                LEFT JOIN "wgr_sp_lieferant" lief ON geraet.id_lieferant=lief.fid
                WHERE geraet.fid=%s''', (row["playdevice_fid"],)).fetchone()
            if not device_row:
                return Response.text("Zugehöriges Spielgerät nicht gefunden.", 404)
            picture_rows = db.execute('''SELECT tid, picture_base64 AS picture
                FROM "wgr_sp_insp_mangel_foto" WHERE tid_maengel=%s ORDER BY tid''', (tid,)).fetchall()
            attachments = []
            for index, picture in enumerate(picture_rows, 1):
                data, mime = _decode_image(picture.get("picture"))
                if data:
                    if mime not in ALLOWED_IMAGE_MIME_TYPES:
                        return Response.text("Ungültiger Bildtyp in den Mängelfotos.", 400)
                    ext = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}[mime]
                    attachments.append(MailAttachment(f"Mangel-{tid}-Foto-{index}.{ext}", mime, data))
            message = compose_defect_mail(row, device_row, recipient, user, attachments)
            recipient_fid = recipient["fid"]
        # No database transaction is held open during the external SMTP call.
        deliver(message, recipient["email"])
        with connect() as db:
            db.execute('''UPDATE "wgr_sp_insp_mangel" SET
                infomail_gesendet_am=CURRENT_TIMESTAMP, infomail_empfaenger=%s
                WHERE tid=%s AND fid_zustaendig_kontrolleur=%s''',
                (recipient["name"], tid, recipient_fid))
            updated = db.execute(DEFECT_SELECT + " WHERE tid=%s", (tid,)).fetchone()
            result = _defect_dict(db, updated) if updated else None
        return Response.json(result)
    except (OSError, TimeoutError, MailConfigurationError, __import__("smtplib").SMTPException) as exc:
        import logging
        logging.getLogger(__name__).error("Infomail for defect %s failed: %s", tid, exc)
        return Response.text("Infomail konnte nicht an den Mailserver übergeben werden.", 502)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Infomail error for defect %s", tid)
        return Response.text("Infomail konnte nicht abgeschlossen werden. Bitte Versandstatus prüfen.", 500)


def _decode_image(value: bytes | str | None) -> tuple[bytes | None, str | None]:
    if value is None:
        return None, None
    raw = value if isinstance(value, bytes) else value.encode()
    printable = bool(raw) and all(32 <= byte <= 126 or byte in (9, 10, 13) for byte in raw[:128])
    if printable:
        text = raw.decode("utf-8", "replace").strip()
        if len(text) >= 16 and len(text) % 2 == 0 and all(char in "0123456789abcdefABCDEF" for char in text):
            try:
                text = bytes.fromhex(text).decode("utf-8").strip()
            except Exception:
                pass
        mime = None
        if text.lower().startswith("data:") and "," in text:
            meta, text = text.split(",", 1)
            mime = meta[5:].split(";", 1)[0]
        try:
            raw = base64.b64decode(text.replace(" ", "+") + "=" * (-len(text) % 4), validate=False)
        except (ValueError, binascii.Error):
            return None, None
        return raw, mime or _mime(raw)
    return raw, _mime(raw)


def _mime(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _image_upload_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "Bilddaten fehlen."
    text = value.strip()
    declared_mime = None
    if text.lower().startswith("data:") and "," in text:
        meta, text = text.split(",", 1)
        declared_mime = meta[5:].split(";", 1)[0].lower()
        if ";base64" not in meta.lower():
            return "Bilddaten müssen Base64-kodiert sein."
    try:
        raw = base64.b64decode(text.replace(" ", "+") + "=" * (-len(text) % 4), validate=True)
    except (ValueError, binascii.Error):
        return "Bilddaten sind nicht gültig Base64-kodiert."
    if len(raw) > IMAGE_MAX_BYTES:
        return "Bild ist zu gross (maximal 10 MB)."
    mime = _mime(raw)
    if mime not in ALLOWED_IMAGE_MIME_TYPES:
        return "Nicht unterstützter Bildtyp."
    if declared_mime and declared_mime != mime:
        return "Angegebener Bildtyp stimmt nicht mit den Bilddaten überein."
    return None


def _image_request_too_large(request: Request) -> bool:
    try:
        return int(request.environ.get("CONTENT_LENGTH") or 0) > IMAGE_REQUEST_MAX_BYTES
    except (TypeError, ValueError):
        return False


def get_playdevice_picture(request: Request) -> Response:
    if _bool(request.query.get("dryRun")):
        return Response(b"", 200, "application/json; charset=utf-8")
    _, error = require_user(request)
    if error:
        return error
    with connect() as db:
        row = db.execute('SELECT picture_base64 AS picture FROM "gr_v_spielgeraete" WHERE fid=%s',
                         (int(request.params["fid"]),)).fetchone()
    if not row or row["picture"] is None:
        return Response.text("Kein Bild vorhanden.", 404)
    data, mime = _decode_image(row["picture"])
    return Response.file(data, mime) if data else Response.text("Kein Bild vorhanden.", 404)


def exchange_playdevice_picture(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    fid = int(request.query.get("fid") or 0)
    if fid < 1:
        return Response.json({"errorMessage": "SPK-7"})
    if _image_request_too_large(request):
        return Response.text("Bild-Upload ist zu gross.", 413)
    body = request.json() or {}
    data = body.get("data") if "data" in body else body.get("Data")
    data = data.strip() if isinstance(data, str) else data
    if not data:
        return Response.json({"errorMessage": "SPK-6"})
    image_error = _image_upload_error(data)
    if image_error:
        return Response.text(image_error, 400)
    if not _bool(request.query.get("dryRun")):
        with connect() as db:
            db.execute('UPDATE "gr_v_spielgeraete" SET picture_base64=%s WHERE fid=%s',
                       (str(data).encode("ascii", "replace"), fid))
    return Response.json({"errorMessage": ""})


def put_playdevice_picture(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    if _bool(request.query.get("dryRun")):
        return Response(b"", 200, "application/json; charset=utf-8")
    if _image_request_too_large(request):
        return Response.text("Bild-Upload ist zu gross.", 413)
    body = request.json() or {}
    data = body.get("data") if "data" in body else body.get("Data")
    image_error = _image_upload_error(data)
    if image_error:
        return Response.text(image_error, 400)
    with connect() as db:
        db.execute('UPDATE "gr_v_spielgeraete" SET picture_base64=%s WHERE fid=%s',
                   (data, int(request.params["fid"])))
    return Response(b"", 200, "application/json; charset=utf-8")


def get_defect_picture(request: Request) -> Response:
    if _bool(request.query.get("dryRun")):
        return Response(b"", 200, "application/json; charset=utf-8")
    _, error = require_user(request)
    if error:
        return error
    column = "picture_base64_thumb" if _bool(request.query.get("thumb")) else "picture_base64"
    with connect() as db:
        row = db.execute(f'SELECT {column} AS value FROM "wgr_sp_insp_mangel_foto" WHERE tid=%s',
                         (int(request.params["tid"]),)).fetchone()
    if not row or row["value"] is None:
        return Response.text("Kein Bild vorhanden.", 404)
    data, mime = _decode_image(row["value"])
    return Response.file(data, mime) if data else Response.text("Kein Bild vorhanden.", 404)


def put_defect_picture(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    if _image_request_too_large(request):
        return Response.text("Bild-Upload ist zu gross.", 413)
    body = request.json() or {}
    picture = body.get("base64StringPicture") or ""
    thumbnail = body.get("base64StringPictureThumb") or ""
    for value in (picture, thumbnail):
        image_error = _image_upload_error(value)
        if image_error:
            return Response.text(image_error, 400)
    with connect() as db:
        db.execute('LOCK TABLE "wgr_sp_insp_mangel_foto" IN EXCLUSIVE MODE')
        row = db.execute('''INSERT INTO "wgr_sp_insp_mangel_foto"
            (tid, tid_maengel, picture_base64, picture_base64_thumb, zeitpunkt)
            VALUES ((SELECT COALESCE(MAX(tid),0)+1 FROM "wgr_sp_insp_mangel_foto"), %s, %s, %s, %s)
            RETURNING tid''',
            (int(request.params["tid"]), picture, thumbnail, _bool(body.get("afterFixing"))),
        ).fetchone()
    return Response.json({"tid": row["tid"]}) if row else Response(b"", 400)


def post_inspections(request: Request) -> Response:
    user = current_user(request, dry_run=_bool(request.query.get("dryRun")))
    if not user:
        return Response.text("Unauthorized", 401)
    if user.get("role") == "maintenance":
        return Response.text("Benutzer der Rolle Wartung dürfen keine Kontrollen durchführen.", 403)
    reports = request.json()
    if not isinstance(reports, list) or not reports:
        return Response.json({"errorMessage": "SPK-0"})
    inspection_type = reports[0].get("inspectionType") or ""
    if not inspection_type or any(report.get("inspectionType") != inspection_type for report in reports):
        return Response.json({"errorMessage": "SPK-6"})
    base_type = inspection_type[:-5] if len(inspection_type) > 4 else inspection_type
    service_date = date.today()
    try:
        with connect() as db:
            inspector = db.execute('SELECT fid FROM "wgr_sp_kontrolleur" WHERE trim(lower(e_mail))=%s',
                                   (user["mailAddress"],)).fetchone()
            type_row = db.execute('SELECT id FROM "wgr_sp_inspektionsart_tbd" WHERE value=%s',
                                  (base_type,)).fetchone()
            first_fid = int(reports[0].get("playdeviceFid") or 0)
            playground = db.execute('SELECT fid_spielplatz FROM "gr_v_spielgeraete" WHERE fid=%s',
                                    (first_fid,)).fetchone()
            inspector_fid = inspector["fid"] if inspector else None
            type_id = type_row["id"] if type_row else None
            playground_fid = playground["fid_spielplatz"] if playground else None
            if not inspector_fid or not type_id or not playground_fid:
                return Response.json({"errorMessage": "SPK-11"})
            authorized = db.execute(
                '''SELECT 1 FROM "wgr_sp_inspart_kontr"
                   WHERE fid_kontrolleur=%s AND fid_spielplatz=%s AND id_inspektionsart=%s
                   LIMIT 1''',
                (inspector_fid, playground_fid, type_id),
            ).fetchone()
            if not authorized:
                return Response.json({"errorMessage": "SPK-11"})
            for report in reports:
                fid = int(report.get("playdeviceFid") or 0)
                if not fid:
                    return Response.json({"errorMessage": "SPK-12"})
                device_playground = db.execute(
                    'SELECT fid_spielplatz FROM "gr_v_spielgeraete" WHERE fid=%s', (fid,)
                ).fetchone()
                if not device_playground or device_playground["fid_spielplatz"] != playground_fid:
                    return Response.json({"errorMessage": "SPK-12"})
            db.execute('LOCK TABLE "wgr_sp_inspektion", "wgr_sp_insp_bericht" IN EXCLUSIVE MODE')
            duplicate = db.execute(
                '''SELECT 1 FROM "wgr_sp_inspektion"
                   WHERE fid_spielplatz=%s AND id_inspektionsart=%s AND datum_inspektion::date=%s
                   LIMIT 1''',
                (playground_fid, type_id, service_date),
            ).fetchone()
            if duplicate:
                return Response.json({"errorMessage": "SPK-2"})
            target = None
            target_column = {1: "dat_naech_visu_insp", 2: "dat_naech_oper_insp", 3: "dat_naech_haupt_insp"}.get(type_id)
            if target_column and playground_fid:
                target_row = db.execute(
                    f'SELECT ({target_column})::date AS target FROM "wgr_sp_spielplatz" WHERE fid=%s',
                    (playground_fid,),
                ).fetchone()
                target = target_row["target"] if target_row else None
            inserted = db.execute('''INSERT INTO "wgr_sp_inspektion"
                (tid, id_inspektionsart, fid_spielplatz, datum_inspektion, fid_kontrolleur, datum_soll_inspektion)
                VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_inspektion"),
                        %s, %s, %s, %s, %s) RETURNING tid''',
                (type_id, playground_fid, service_date, inspector_fid, target),
            ).fetchone()
            inspection_tid = inserted["tid"]
            for report in reports:
                fid = int(report.get("playdeviceFid") or 0)
                if not fid:
                    raise ValueError("Missing playdevice fid")
                device = db.execute(
                    'SELECT nicht_zu_pruefen, nicht_pruefbar FROM "gr_v_spielgeraete" WHERE fid=%s', (fid,)
                ).fetchone()
                if not device or device.get("nicht_zu_pruefen") or device.get("nicht_pruefbar"):
                    continue
                db.execute('''INSERT INTO "wgr_sp_insp_bericht"
                    (tid, tid_inspektion, fid_spielgeraet, fid_geraet_detail, inspektionsart,
                     datum_inspektion, kontrolleur, pruefung_text, pruefung_erledigt,
                     pruefung_kommentar, wartung_text, wartung_erledigung, wartung_kommentar, fallschutz)
                    VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_insp_bericht"),
                     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (inspection_tid, fid, report.get("playdeviceDetailFid") or None, inspection_type, service_date,
                     f"{user['firstName']} {user['lastName']}", report.get("inspectionText") or "",
                     1 if _bool(report.get("inspectionDone")) else 0, report.get("inspectionComment") or "",
                     report.get("maintenanceText") or "", 1 if _bool(report.get("maintenanceDone")) else 0,
                     report.get("maintenanceComment") or "", report.get("fallProtectionType") or ""),
                )
        return Response.json({"errorMessage": ""})
    except Exception:
        return Response.json({"errorMessage": "SPK-3"})


def get_document(request: Request) -> Response:
    _, error = require_user(request)
    if error:
        return error
    kind = request.query.get("type", "").strip().lower()
    storage = _document_storage(kind)
    if not storage:
        return Response(b"", 400)
    table, column = storage
    try:
        with connect() as db:
            row = db.execute(f'SELECT {column} AS content FROM "{table}" WHERE fid=%s',
                             (int(request.params["fid"]),)).fetchone()
        if not row:
            return Response(b"", 400)
        content, _ = _document_parts(row["content"])
        return Response.file(content, "application/pdf")
    except Exception:
        return Response(b"", 400)


def post_document(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    body = request.json() or {}
    kind = str(body.get("type") or "").strip().lower()
    storage = _document_storage(kind)
    name = str(body.get("name") or "").strip()
    try:
        playground_id = int(body.get("playgroundId"))
        content = base64.b64decode(str(body.get("contentBase64") or ""), validate=True)
    except (TypeError, ValueError, binascii.Error):
        return Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400)
    if not storage or playground_id <= 0 or not name or len(name) > 255:
        return Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400)
    if len(content) > DOCUMENT_MAX_BYTES or not content.startswith(b"%PDF-"):
        return Response.json({"errorMessage": "Es sind nur PDF-Dokumente bis 20 MB zulässig."}, 400)
    table, column = storage
    try:
        with connect() as db:
            db.execute(f'LOCK TABLE "{table}" IN EXCLUSIVE MODE')
            next_row = db.execute(f'SELECT COALESCE(MAX(fid), 0) + 1 AS fid FROM "{table}"').fetchone()
            fid = int(next_row["fid"])
            db.execute(
                f'INSERT INTO "{table}" (fid, fid_spielplatz, {column}) VALUES (%s, %s, %s)',
                (fid, playground_id, _document_with_name(content, name)),
            )
        return Response.json({"fid": fid, "name": name})
    except Exception:
        return Response.json({"errorMessage": "Dokument konnte nicht gespeichert werden."}, 400)


def rename_document(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    kind = request.query.get("type", "").strip().lower()
    storage = _document_storage(kind)
    body = request.json() or {}
    name = str(body.get("name") or "").strip()
    if not storage or not name or len(name) > 255:
        return Response.json({"errorMessage": "Ungültiger Dokumentname."}, 400)
    table, column = storage
    try:
        fid = int(request.params["fid"])
        with connect() as db:
            row = db.execute(f'SELECT {column} AS content FROM "{table}" WHERE fid=%s', (fid,)).fetchone()
            if not row or not row.get("content"):
                return Response.json({"errorMessage": "Dokument nicht gefunden."}, 404)
            db.execute(f'UPDATE "{table}" SET {column}=%s WHERE fid=%s',
                       (_document_with_name(row["content"], name), fid))
        return Response.json({"fid": fid, "name": name})
    except Exception:
        return Response.json({"errorMessage": "Dokumentname konnte nicht gespeichert werden."}, 400)


def delete_document(request: Request) -> Response:
    _, error = require_user(request, "administrator")
    if error:
        return error
    kind = request.query.get("type", "").strip().lower()
    storage = _document_storage(kind)
    if not storage:
        return Response.json({"errorMessage": "Ungültiger Dokumenttyp."}, 400)
    table, _ = storage
    try:
        fid = int(request.params["fid"])
        with connect() as db:
            row = db.execute(
                f'DELETE FROM "{table}" WHERE fid=%s RETURNING fid', (fid,)
            ).fetchone()
            if not row:
                return Response.json({"errorMessage": "Dokument nicht gefunden."}, 404)
        return Response.json({"fid": fid})
    except Exception:
        return Response.json({"errorMessage": "Dokument konnte nicht gelöscht werden."}, 400)


def push_register(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    body = request.json() or {}
    try:
        endpoint = body["endpoint"].strip()
        p256dh = body["p256dh"].strip()
        auth = body["auth"].strip()
        if not endpoint or not p256dh or not auth:
            raise ValueError("Incomplete subscription")
        with connect() as db:
            db.execute('''INSERT INTO "wgr_sp_push_subscription"
                (fid_kontrolleur, endpoint, p256dh, auth, user_agent, aktiv,
                 datum_registrierung, datum_letzte_verwendung, datum_deaktivierung)
                VALUES (%s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP, NULL, NULL)
                ON CONFLICT (endpoint) DO UPDATE SET
                 fid_kontrolleur=EXCLUDED.fid_kontrolleur, p256dh=EXCLUDED.p256dh,
                 auth=EXCLUDED.auth, user_agent=EXCLUDED.user_agent, aktiv=true,
                 datum_letzte_verwendung=CURRENT_TIMESTAMP, datum_deaktivierung=NULL''',
                (user["fid"], endpoint, p256dh, auth, (body.get("userAgent") or request.headers.get("User-Agent", "")).strip() or None),
            )
        return Response.json({"errorMessage": ""})
    except Exception:
        return Response.json({"errorMessage": "SPK-3"})


def push_unregister(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    body = request.json() or {}
    try:
        endpoint = (body.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("Missing endpoint")
        with connect() as db:
            db.execute('''UPDATE "wgr_sp_push_subscription"
                SET aktiv=false, datum_deaktivierung=CURRENT_TIMESTAMP
                WHERE fid_kontrolleur=%s AND endpoint=%s''', (user["fid"], endpoint))
        return Response.json({"errorMessage": ""})
    except Exception:
        return Response.json({"errorMessage": "SPK-3"})


def push_me(request: Request) -> Response:
    user, error = require_user(request)
    if error:
        return error
    with connect() as db:
        rows = db.execute('''SELECT endpoint, p256dh, auth, COALESCE(user_agent,'') AS user_agent
            FROM "wgr_sp_push_subscription" WHERE fid_kontrolleur=%s AND aktiv=true''', (user["fid"],)).fetchall()
    return Response.json([{
        "endpoint": row["endpoint"], "p256dh": row["p256dh"], "auth": row["auth"], "userAgent": row["user_agent"]
    } for row in rows])
