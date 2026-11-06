import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class DeviceCardTemplateTests(unittest.TestCase):
    def test_legacy_feature_contract_used_in_cards(self):
        source = (ROOT / 'src/playground_check/django_project/ui_templates/detail.html').read_text()
        self.assertIn('device.properties', source)
        self.assertIn('p.type.description', source)
        self.assertIn('p.fid', source)
        self.assertIn('/Playdevice/{{ p.fid }}/Picture/', source)
        self.assertIn('loading="lazy"', source)

    def test_defect_description_uses_actual_legacy_field(self):
        source = (ROOT / 'src/playground_check/django_project/ui_templates/detail.html').read_text()
        self.assertIn("defect.defectDescription|ui_default:'Mangel'", source)
        self.assertNotIn('defect.beschreibung', source)
        self.assertNotIn('defect.description|default:', source)

    def test_each_defect_links_to_its_own_editor_under_base_path(self):
        from unittest.mock import patch
        from django.test import RequestFactory
        from playground_check.django_project import python_ui as ui

        payload = {'name': 'Musterpark', 'playdevices': [{'properties': {
            'fid': 42, 'type': {'description': 'Schaukel', 'name': 'Schaukel'},
            'defects': [
                {'tid': 2471, 'defectDescription': 'Schraube locker'},
                {'tid': 2599, 'defectDescription': 'Kette beschädigt'},
            ],
        }}]}
        with patch.object(ui, 'require_user', return_value=({'fid': 17, 'role': 'inspector'}, None)), \
             patch.object(ui, 'playground_by_name_data', return_value=payload):
            response = ui.playground_detail(RequestFactory().get(
                '/detail/', {'name': 'Musterpark'}, SCRIPT_NAME='/stadtgruen/spielplatzkontrolle'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('href="/stadtgruen/spielplatzkontrolle/defect/?tid=2471">Schraube locker</a>', html)
        self.assertIn('href="/stadtgruen/spielplatzkontrolle/defect/?tid=2599">Kette beschädigt</a>', html)
        self.assertIn('href="/stadtgruen/spielplatzkontrolle/defect/edit/?playdeviceFid=42"', html)

    def test_card_links_keep_reverse_proxy_prefix(self):
        source = (ROOT / 'src/playground_check/django_project/ui_templates/detail.html').read_text()
        for path in ('/device/edit/', '/device/photo/', '/defect/edit/'):
            self.assertIn('{{ prefix }}' + path, source)

if __name__ == '__main__':
    unittest.main()


class DeviceCardDisplayTests(unittest.TestCase):
    def test_attributes_status_and_contextual_actions(self):
        from datetime import date
        from unittest.mock import patch
        from django.test import RequestFactory
        from playground_check.django_project import python_ui as ui
        for construction, year, planned in [(date(2017, 6, 2), '2017', True),
                                            ('2019-03-01T00:00:00', '2019', False),
                                            ('0001-01-01T00:00:00', 'Nicht angegeben', False)]:
            with self.subTest(construction=construction):
                properties = {'fid': 42, 'type': {'description': 'Schaukel', 'name': 'Schaukel', 'standard': 'SN EN 1176:2017'},
                              'supplier': 'Lieferant A', 'constructionDate': construction,
                              'recommendedYearOfRenovation': 2030 if planned else 0,
                              'renovationType': 2, 'commentRecommendedYearOfRenovation': 'Ersatz vorsehen',
                              'defects': [{'defectDescription': 'Schraube locker'}] if planned else []}
                payload = {'name': 'Musterpark', 'playdevices': [{'properties': properties}],
                           'renovationTypeOptions': [{'id': 2, 'value': 'Ersatz'}]}
                with patch.object(ui, 'require_user', return_value=({'fid': 17, 'role': 'inspector'}, None)), \
                     patch.object(ui, 'playground_by_name_data', return_value=payload):
                    response = ui.playground_detail(RequestFactory().get('/detail/', {'name': 'Musterpark'},
                                                       SCRIPT_NAME='/stadtgruen/spielplatzkontrolle'))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                attributes = html.split('class="device-card-section device-attributes"', 1)[1].split('</section>', 1)[0]
                defects = html.split('class="device-card-section device-defect-section"', 1)[1].split('</details>', 1)[0]
                for label in ['Norm (Jahrgang)', 'Lieferant', 'Erstellungsjahr', 'Empfohlenes Sanierungsjahr',
                              'Sanierungsart', 'Kommentar zu empf. Sanierungsjahr']:
                    self.assertIn(label, attributes)
                self.assertIn('SN EN 1176:2017', attributes)
                self.assertIn('Lieferant A', attributes)
                self.assertIn('Ersatz', attributes)
                self.assertEqual(properties['construction_year'], int(year) if year.isdigit() else None)
                self.assertIn('Sanierung ausstehend' if planned else 'Keine Sanierung geplant', attributes)
                self.assertIn('/stadtgruen/spielplatzkontrolle/device/edit/', attributes)
                self.assertNotIn('Mangel erfassen', attributes)
                self.assertIn('/stadtgruen/spielplatzkontrolle/defect/edit/', defects)
                self.assertIn('Schraube locker' if planned else 'Keine offenen Mängel erfasst.', defects)
                self.assertNotIn('Spielgerät bearbeiten', html)


class DeviceCardRenovationAndDefectsTests(unittest.TestCase):
    def test_stamp_year_boundaries_and_collapsed_defects(self):
        from datetime import date
        from html.parser import HTMLParser
        from unittest.mock import patch
        from django.test import RequestFactory
        from playground_check.django_project import python_ui as ui

        class CardParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stamps = []
                self.defect_sections = []
                self.summaries = 0
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                classes = attrs.get('class', '').split()
                if 'renovation-stamp' in classes:
                    self.stamps.append(classes)
                if tag == 'details' and 'device-defect-section' in classes:
                    self.defect_sections.append(attrs)
                if tag == 'summary':
                    self.summaries += 1

        cases = [(None, 'unplanned'), ('', 'unplanned'), (0, 'unplanned'), ('0', 'unplanned'),
                 (2031, 'urgent'), (2032, 'urgent'), (2033, 'urgent'),
                 (2034, 'future'), (2040, 'future')]
        for current_year in (2032, 2033):
            for year, expected in cases:
                # Advancing the business year also changes the stamp at the boundary.
                if current_year == 2033 and year == 2034:
                    expected = 'urgent'
                with self.subTest(current_year=current_year, year=year):
                    props = {'fid': 42, 'type': {'description': 'Schaukel', 'name': 'Schaukel'},
                             'recommendedYearOfRenovation': year,
                             'defects': [{'defectDescription': 'Schraube locker'}]}
                    payload = {'name': 'Musterpark', 'playdevices': [{'properties': props}]}
                    with patch.object(ui, 'require_user', return_value=({'fid': 17, 'role': 'inspector'}, None)), \
                         patch.object(ui, 'playground_by_name_data', return_value=payload), \
                         patch.object(ui, 'local_today', return_value=date(current_year, 1, 1)):
                        response = ui.playground_detail(RequestFactory().get('/detail/', {'name': 'Musterpark'}))
                    self.assertEqual(response.status_code, 200)
                    html = response.content.decode()
                    parsed = CardParser()
                    parsed.feed(html)
                    self.assertEqual(parsed.stamps, [['renovation-stamp', 'is-' + expected]])
                    self.assertEqual(len(parsed.defect_sections), 1)
                    self.assertNotIn('open', parsed.defect_sections[0])
                    self.assertGreaterEqual(parsed.summaries, 2)
                    self.assertIn('Keine Sanierung geplant' if expected == 'unplanned' else 'Sanierung ausstehend', html)
                    self.assertIn('Schraube locker', html)
                    self.assertIn('/defect/edit/?playdeviceFid=42', html)
