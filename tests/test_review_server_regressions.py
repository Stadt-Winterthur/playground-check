"""Review findings F01-F04, F09-F10 and F19-F23: behavioural regressions."""
import json
import os
import unittest
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.test import RequestFactory
from playground_check import inspection_submission as submission, device_detail_batch as batch
from playground_check import domain_support as service, inspection_defect_service, defect_write_repository
from playground_check.django_project import inspection_device_commands as commands, account_commands

KIND = 'Visuelle Inspektion (VI)'
USER = {'fid': 17, 'role': 'inspector', 'mailAddress': 'test@example.org', 'firstName': 'Test', 'lastName': 'Person'}
REPORT = {'playdeviceFid': 42, 'inspectionType': KIND, 'inspectionText': 'Prüfen',
          'maintenanceText': 'Warten', 'fallProtectionType': '', 'inspectionDone': True,
          'maintenanceDone': True, 'inspectionComment': 'Kommentar'}


class CanonicalInspectionTests(unittest.TestCase):
    def validate(self, reports, *, devices=None, playground=None):
        with patch.object(submission.playground_repository, 'playdevice_rows', return_value=devices or [{'fid': 42}]), \
             patch.object(batch, 'criteria_for_devices', return_value={submission.GROUPS[0][0]: {42: [{'check_text': 'Prüfen', 'maintenance': 'Warten'}]}}):
            return submission.validate_reports(object(), playground or {'id': 1}, KIND, reports)

    def test_complete_report_preserves_only_allowed_values(self):
        result = self.validate([{**REPORT, 'playdeviceDetailFid': 999, 'untrusted': 'text'}])
        self.assertEqual(result[0]['inspectionComment'], 'Kommentar')
        self.assertNotIn('untrusted', result[0])
        self.assertNotIn('playdeviceDetailFid', result[0])

    def test_incomplete_unknown_and_duplicate_reports_rejected(self):
        cases = [[], [REPORT, REPORT], [{**REPORT, 'inspectionText': 'Erfunden'}],
                 [{**REPORT, 'playdeviceFid': 999}], [{**REPORT, 'inspectionDone': False}],
                 [{**REPORT, 'maintenanceDone': 'true'}], [{**REPORT, 'inspectionComment': 'x' * 2001}],
                 [{**REPORT, 'maintenanceComment': []}]]
        for reports in cases:
            with self.subTest(reports=reports), self.assertRaises(ValueError):
                self.validate(reports)

    def test_suspend_interval_and_unreasoned_device_rejected(self):
        with self.assertRaises(ValueError):
            self.validate([REPORT], playground={'id': 1, 'suspend_from': date.today() - timedelta(days=1)})
        with self.assertRaises(ValueError):
            self.validate([REPORT], devices=[{'fid':42, 'cannot_be_checked':True}])

    def test_exempt_devices_need_no_report_but_reason_is_retained(self):
        result = self.validate([REPORT], devices=[{'fid':42}, {'fid':43,'cannot_be_checked':True,'cannot_be_checked_reason':'Umbau'}])
        self.assertEqual(len(result), 1)

    def test_api_validation_failure_never_inserts_header_or_child(self):
        for failure, status, code in (
            (commands.InspectionValidationError('incomplete'), 400, 'SPK-13'),
            (TypeError('internal defect'), 500, 'SPK-3'),
            (KeyError('internal defect'), 500, 'SPK-3'),
        ):
            db = MagicMock();db.__enter__.return_value = db
            rf = RequestFactory()
            request = rf.post('/Inspection/', json.dumps([REPORT]), content_type='application/json')
            with ExitStack() as stack:
                stack.enter_context(patch.object(service, 'current_user', return_value=USER))
                stack.enter_context(patch.object(service, 'connect', return_value=db))
                for name,value in [('inspector',{'fid':17}), ('inspection_type',{'id':1,'value':'Visuelle Inspektion','short_value':'VI'}),
                                   ('device_playground',{'fid_spielplatz':1}), ('is_authorized',True)]:
                    stack.enter_context(patch.object(service.inspection_validation_repository,name,return_value=value))
                stack.enter_context(patch.object(commands,'playground_by_fid',return_value={'id':1}))
                stack.enter_context(patch.object(commands,'validate_reports',side_effect=failure))
                parent=stack.enter_context(patch.object(service.inspection_write_repository,'insert_inspection'))
                child=stack.enter_context(patch.object(service.inspection_write_repository,'insert_report'))
                response=commands.create_inspection(request)
            self.assertEqual(response.status_code,status)
            self.assertEqual(json.loads(response.content)['errorMessage'],code)
            parent.assert_not_called();child.assert_not_called()

    def test_api_complete_inspection_writes_validated_data(self):
        db=MagicMock();db.__enter__.return_value=db
        with ExitStack() as stack:
            stack.enter_context(patch.object(service,'current_user',return_value=USER))
            stack.enter_context(patch.object(service,'connect',return_value=db))
            for name,value in [('inspector',{'fid':17}),('inspection_type',{'id':1,'value':'Visuelle Inspektion','short_value':'VI'}),
                ('device_playground',{'fid_spielplatz':1}),('is_authorized',True),('duplicate_inspection',None),
                ('target_date_row',None),('device_check_state',{'nicht_zu_pruefen':False,'nicht_pruefbar':False})]:
                stack.enter_context(patch.object(service.inspection_validation_repository,name,return_value=value))
            stack.enter_context(patch.object(commands,'playground_by_fid',return_value={'id':1}))
            stack.enter_context(patch.object(commands,'validate_reports',return_value=[REPORT]))
            stack.enter_context(patch.object(service.inspection_write_repository,'insert_inspection',return_value=123))
            child=stack.enter_context(patch.object(service.inspection_write_repository,'insert_report'))
            response=commands.create_inspection(RequestFactory().post('/Inspection/',json.dumps([REPORT]),content_type='application/json'))
        self.assertEqual(json.loads(response.content),{'errorMessage':''})
        self.assertEqual(child.call_args.args[3],REPORT)


class DeviceWriteAuthorizationTests(unittest.TestCase):
    def test_maintenance_denied_for_every_device_write_before_repository_access(self):
        rf=RequestFactory()
        for fn,args in [(commands.save_playdevice,()),(commands.exchange_playdevice_picture,()),(commands.put_playdevice_picture,(42,))]:
            with self.subTest(fn=fn.__name__),patch.object(service,'require_user',return_value=({**USER,'role':'maintenance'},None)),patch.object(service,'connect') as db:
                r=fn(rf.put('/Playdevice/?fid=42','{}',content_type='application/json'),*args)
                self.assertEqual(r.status_code,403);db.assert_not_called()

    def test_missing_photo_returns_local_placeholder(self):
        db=MagicMock();db.__enter__.return_value=db
        with patch.object(service,'require_user',return_value=(USER,None)),patch.object(service,'connect',return_value=db),patch.object(service.remaining_reads_repository,'playdevice_picture',return_value={'picture':None}):
            response=commands.get_playdevice_picture(RequestFactory().get('/Playdevice/42/Picture/'),42)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'image/svg+xml')
        self.assertIn(b'<svg', response.content)
        self.assertNotIn(b'<text', response.content)


class TransactionAndHistoryTests(unittest.TestCase):
    def test_invalid_password_never_opens_write_transaction(self):
        r=RequestFactory().put('/Account/Users/?changePassphrase=true',json.dumps({'mailAddress':'other@example.org','role':'inspector','active':True,'passPhrase':'short'}),content_type='application/json')
        with patch.object(service,'require_user',return_value=({**USER,'role':'administrator'},None)),patch.object(service,'connect') as db:
            result=account_commands.update_user(r)
        self.assertEqual(json.loads(result.content),{'errorMessage':'SPK-9'});db.assert_not_called()

    def test_unexpected_password_update_rolls_back(self):
        db=MagicMock();db.__enter__.return_value=db
        r=RequestFactory().put('/Account/Users/?changePassphrase=true',json.dumps({'mailAddress':'other@example.org','role':'inspector','active':True,'passPhrase':'long-password'}),content_type='application/json')
        with patch.object(service,'require_user',return_value=({**USER,'role':'administrator'},None)),patch.object(service,'connect',return_value=db),patch.object(service.user_repository,'users_by_email',return_value=[{'role':'inspector'}]),patch.object(service.user_write_repository,'active_admin_count',return_value=2),patch.object(service.user_write_repository,'update_user',return_value=1),patch.object(service.user_write_repository,'update_password',return_value=0):
            result=account_commands.update_user(r)
        self.assertEqual(json.loads(result.content),{'errorMessage':'SPK-3'})
        self.assertIs(db.__exit__.call_args.args[0],ValueError)

    def test_one_history_group_is_latest(self):
        recent,previous=inspection_defect_service.inspection_history(None,42,[KIND],load_reports=lambda *a:[{'inspection_tid':5,'tid':2}],serialize_report=dict)
        self.assertEqual(recent,[{'inspection_tid':5,'tid':2}]);self.assertEqual(previous,[])

    def test_completion_sql_preserves_existing_provenance(self):
        db=MagicMock()
        defect_write_repository.update_defect(db,{'tid':1},date(2026,1,1),None,None,None,None,None,17)
        sql,params=db.execute.call_args.args
        self.assertIn('COALESCE(fid_erledigung, %s::varchar)',sql)
        self.assertIn('COALESCE(datum_erledigung, %s)',sql)
        self.assertEqual(len(params),sql.count('%s'))

    def test_large_form_parses_and_remains_bounded(self):
        from urllib.parse import urlencode
        from django.conf import settings
        r=RequestFactory().post('/inspection/',urlencode({str(i):'x' for i in range(8006)}),content_type='application/x-www-form-urlencoded')
        self.assertEqual(len(r.POST),8006)
        self.assertEqual(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS,9000)

    def test_batch_detail_query_count_does_not_grow_with_devices(self):
        class DB:
            def __init__(self):self.calls=[]
            def execute(self,sql,params=None):self.calls.append(sql);return self
            def fetchall(self):return []
        counts=[]
        for n in (1,50):
            db=DB();result=batch.build_devices(db,[{'fid':i} for i in range(n)],KIND,True,True,'')
            self.assertEqual(len(result),n);counts.append(len(db.calls))
        self.assertEqual(counts,[6,6])

    def test_search_escapes_literals_and_open_intervals(self):
        from playground_check.remaining_reads_repository import gui_playground_page,gui_defect_page
        db=MagicMock();db.execute.return_value.fetchall.return_value=[]
        gui_playground_page(db,USER,KIND,'100%_!\\',0,20)
        sql,params=db.execute.call_args.args
        self.assertIn("ESCAPE '!'",sql);self.assertEqual(params[2],'%100!%!_!!\\%')
        self.assertIn('inspektion_aussetzen_bis IS NULL OR',sql)
        gui_defect_page(db,'100%_!', 'open',0,20)
        self.assertEqual(db.execute.call_args.args[1][3],'%100!%!_!!%')

    def test_compatibility_defaults_to_correct_options(self):
        from playground_check.config import Settings
        with patch.dict(os.environ):
            os.environ.pop('PLAYGROUND_COMPATIBILITY_BUGS',None)
            self.assertFalse(Settings.load().compatibility_bugs)


class AdditionalIntegrityTests(unittest.TestCase):
    def test_stale_defect_edit_is_rejected_before_update(self):
        from playground_check.django_project import defect_commands
        db=MagicMock();db.__enter__.return_value=db
        request=RequestFactory().post('/Defect/',json.dumps({'tid':321,'priority':1,'dateDone':None,'expectedVersion':'old'}),content_type='application/json')
        with patch.object(service,'require_user',return_value=(USER,None)),patch.object(service,'connect',return_value=db),patch.object(service.defect_write_repository,'current_responsible',return_value={'responsible_user_fid':None,'record_version':'new'}),patch.object(service.defect_write_repository,'update_defect') as update:
            response=defect_commands.update_defect(request)
        self.assertEqual(response.status_code,409);update.assert_not_called()

    def test_account_lock_precedes_policy_read(self):
        db=MagicMock();db.__enter__.return_value=db
        calls=[]
        request=RequestFactory().delete('/Account/Users/?email=admin@example.org')
        with patch.object(service,'require_user',return_value=({**USER,'role':'administrator'},None)),patch.object(service,'connect',return_value=db),patch.object(service.user_write_repository,'lock_account_changes',side_effect=lambda db:calls.append('lock')),patch.object(service.user_repository,'users_by_email',side_effect=lambda *a:calls.append('read') or [{'role':'administrator'}]),patch.object(service.user_write_repository,'active_admin_count',return_value=1),patch.object(service.user_write_repository,'deactivate_user') as update:
            response=account_commands.delete_user(request)
        self.assertEqual(calls,['lock','read']);update.assert_not_called()

    def test_business_clock_uses_zurich_date_at_utc_midnight_boundary(self):
        from datetime import datetime,timezone
        from playground_check import business_time
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,1,1,23,30,tzinfo=timezone.utc).astimezone(tz)
        with patch.object(business_time,'datetime',Clock):
            self.assertEqual(business_time.local_today(),date(2026,1,2))
            self.assertEqual(business_time.local_now().hour,0)
            self.assertIsNone(business_time.local_now().tzinfo)

if __name__ == '__main__':
    unittest.main()
