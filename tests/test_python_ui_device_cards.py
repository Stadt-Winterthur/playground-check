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
        self.assertIn("defect.defectDescription|default:'Mangel'", source)
        self.assertNotIn('defect.beschreibung', source)
        self.assertNotIn('defect.description|default:', source)

    def test_card_links_keep_reverse_proxy_prefix(self):
        source = (ROOT / 'src/playground_check/django_project/ui_templates/detail.html').read_text()
        for path in ('/__ui/device/edit/', '/__ui/device/photo/', '/__ui/defect/edit/'):
            self.assertIn('{{ prefix }}' + path, source)

if __name__ == '__main__':
    unittest.main()
