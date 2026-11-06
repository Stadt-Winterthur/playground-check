"""Exercise the real batch SQL against mixed FID types, using temp tables only."""
import os
import unittest

DSN = os.getenv('PLAYGROUND_TEST_POSTGRES_DSN', '')
CONFIRMED = os.getenv('PLAYGROUND_TEST_DATABASE_CONFIRMED') == 'isolated-test-only'

SCHEMA = '''
CREATE TEMP TABLE wgr_sp_kontrolleur(fid bigint PRIMARY KEY, vorname text, nachname text);
CREATE TEMP TABLE wgr_sp_insp_mangel(
    tid bigint, fid_spielgeraet bigint, id_dringlichkeit integer, beschrieb text,
    datum_erledigung timestamp, fid_erledigung varchar, bemerkunng text, datum timestamp,
    id_zustaendig_behebung integer, fid_zustaendig_kontrolleur bigint, auftrag_status text,
    datum_auftrag_zugewiesen timestamp, datum_auftrag_angenommen timestamp,
    datum_auftrag_abgelehnt timestamp, bemerkung_auftrag text,
    infomail_gesendet_am timestamp, infomail_empfaenger text, fid_erfassung bigint);
CREATE TEMP TABLE wgr_sp_mangel_zuweisung_hist(
    id bigint, tid_mangel bigint, geaendert_am timestamp, geaendert_durch_fid bigint,
    geaendert_durch_name text, vorher_fid bigint, vorher_name text, nachher_fid bigint, nachher_name text);
INSERT INTO wgr_sp_kontrolleur VALUES(17, 'Anna', 'Muster');
INSERT INTO wgr_sp_insp_mangel(tid, fid_spielgeraet, beschrieb, fid_erfassung)
    VALUES(321, 42, 'Testmangel', 17);
'''


@unittest.skipUnless(DSN and CONFIRMED, 'Requires an explicitly confirmed isolated PostgreSQL test database')
class BatchFIDTypeTests(unittest.TestCase):
    def test_bigint_users_join_text_completion_ids_without_cast_errors(self):
        import psycopg
        from psycopg.rows import dict_row
        from playground_check.device_detail_batch import defects_for_devices
        with psycopg.connect(DSN, row_factory=dict_row) as db:
            db.execute(SCHEMA)
            for stored, expected in [(None, ''), ('17', 'Anna Muster'), (' 17 ', 'Anna Muster'),
                                     ('', ''), ('unknown', ''), ('999999999999999999999999', '')]:
                with self.subTest(stored=stored):
                    db.execute('UPDATE wgr_sp_insp_mangel SET fid_erledigung=%s', (stored,))
                    result = defects_for_devices(db, [42])
                    self.assertEqual(result[42][0]['createdByName'], 'Anna Muster')
                    self.assertEqual(result[42][0]['doneByName'], expected)
            # Also accept string-based creator IDs without changing the application's schema.
            db.execute('ALTER TABLE wgr_sp_insp_mangel ALTER COLUMN fid_erfassung TYPE varchar USING fid_erfassung::text')
            self.assertEqual(defects_for_devices(db, [42])[42][0]['createdByName'], 'Anna Muster')
            db.rollback()


if __name__ == '__main__':
    unittest.main()
