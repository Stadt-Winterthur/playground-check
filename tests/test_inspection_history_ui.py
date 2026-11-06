"""Complete, read-only history presentation with independent type selection."""
import os
import unittest
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.template import Context
from django.test import RequestFactory
from playground_check.django_project import python_ui
from playground_check.django_project.inspection_history_ui import history_groups, service_date

VI = 'Visuelle Inspektion (VI)'
HI = 'Hauptinspektion (HI)'


class HistoryUITests(unittest.TestCase):
    def test_groups_keep_types_separate_and_include_older_catalog_types(self):
        reports = [{'inspectionType': VI, 'inspectionText': 'Visuell'},
                   {'inspectionType': HI, 'inspectionText': 'Hauptkontrolle'},
                   {'inspectionType': 'Alte Inspektionsart'}]
        groups = history_groups(reports, [VI, HI, VI], HI)
        self.assertEqual([g['kind'] for g in groups], [VI, HI, 'Alte Inspektionsart'])
        self.assertEqual([g['selected'] for g in groups], [False, True, False])
        self.assertEqual(groups[0]['reports'][0]['inspectionText'], 'Visuell')
        self.assertNotIn('service_date_display', reports[0])

    def test_missing_history_retains_selectable_types(self):
        groups = history_groups([], [VI, HI], VI)
        self.assertEqual([g['reports'] for g in groups], [[], []])
        self.assertTrue(groups[0]['selected'])

    def test_service_date_supports_database_and_iso_dates_in_local_time(self):
        for value in (date(2026, 10, 14), datetime(2026, 10, 14, 12),
                      '2026-10-14', '2026-10-14T12:00:00+02:00'):
            self.assertEqual(service_date(value), '14.10.2026')
        self.assertEqual(service_date(datetime(2026, 10, 13, 23, tzinfo=timezone.utc)), '14.10.2026')
        for value in (None, '', 'invalid', '0001-01-01'):
            self.assertEqual(service_date(value), '')

    def test_history_renders_all_legacy_fields_and_disabled_statuses(self):
        report = {'inspectionType': VI, 'inspector': 'Patrick Wittmaier',
                  'dateOfService': '2026-10-14', 'fallProtectionType': 'Hauptfallschutz',
                  'inspectionText': 'Prüfanweisung <script>', 'inspectionDone': True,
                  'inspectionComment': 'Prüfbemerkung\nzweite Zeile',
                  'maintenanceText': 'Wartungsanweisung', 'maintenanceDone': False,
                  'maintenanceComment': 'Wartungsbemerkung'}
        html = python_ui.ENGINE.get_template('inspection_history.html').render(Context({
            'device': {'fid': 42}, 'history_slot': 'last', 'history_title': 'Letzte Kontrolle',
            'history_empty': 'Keine frühere Kontrolle vorhanden.',
            'history_groups': history_groups([report], [VI, HI], VI)}))
        for text in ('Patrick Wittmaier', '14.10.2026', 'Hauptfallschutz',
                     'Prüfanweisung &lt;script&gt;', 'Prüfbemerkung<br>zweite Zeile',
                     'Wartungsanweisung', 'Wartungsbemerkung', 'Metadaten'):
            self.assertIn(text, html)
        class Inputs(HTMLParser):
            def __init__(self):
                super().__init__(); self.inputs = []
            def handle_starttag(self, tag, attrs):
                if tag == 'input': self.inputs.append(dict(attrs))
        parser = Inputs(); parser.feed(html)
        self.assertEqual(len(parser.inputs), 2)
        self.assertTrue(all('disabled' in item and 'name' not in item for item in parser.inputs))
        self.assertIn('checked', parser.inputs[0])
        self.assertNotIn('checked', parser.inputs[1])
        self.assertNotIn('<script>', html)
        self.assertNotIn('<form', html)

    def test_empty_values_use_legacy_fallbacks(self):
        html = python_ui.ENGINE.get_template('inspection_history.html').render(Context({
            'device': {'fid': 42}, 'history_slot': 'previous', 'history_title': 'Vorletzte Kontrolle',
            'history_groups': history_groups([{'inspectionType': VI}], [VI], VI)}))
        for text in ('[Diese Inspektion hat keinen Titel]', '[Kein Kommentar]',
                     '[Die Prüfung dieser Inspektion hat keinen Text]',
                     '[Die Wartung dieser Inspektion hat keinen Text]', 'nein', 'Nicht angegeben'):
            self.assertIn(text, html)

    def test_editor_keeps_last_and_previous_controls_independent(self):
        user = {'fid': 17, 'role': 'inspector', 'mailAddress': 'test@example.invalid'}
        payload = {'inspectionTypeOptions': [VI, HI], 'playdevices': [
            {'fid': 42, 'name': 'Schaukel', 'properties': {
                'lastInspectionReports': [{'inspectionType': VI, 'inspectionText': 'Letzter Bericht'}],
                'nextToLastInspectionReports': [{'inspectionType': HI, 'inspectionText': 'Vorletzter Bericht'}]}}]}
        with patch.object(python_ui, 'require_user', return_value=(user, None)), \
             patch.object(python_ui, 'playground_only_names_data', return_value=[{'name': 'A'}]), \
             patch.object(python_ui, 'playground_by_name_data', return_value=payload):
            result = python_ui.inspection_editor(RequestFactory().get('/inspection/',
                {'name': 'A', 'inspectiontype': VI, 'selected_device': '42'}))
        self.assertEqual(result.status_code, 200)
        html = result.content.decode()
        self.assertIn('id="history-type-42-last"', html)
        self.assertIn('id="history-type-42-previous"', html)
        last = html.split('data-inspection-history="last"', 1)[1].split('data-inspection-history="previous"', 1)[0]
        previous = html.split('data-inspection-history="previous"', 1)[1]
        self.assertIn('Letzter Bericht', last)
        self.assertNotIn('Vorletzter Bericht', last)
        self.assertIn('Vorletzter Bericht', previous)
