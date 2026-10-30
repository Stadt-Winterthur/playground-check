import unittest
from pathlib import Path
from unittest.mock import Mock
from playground_check.playdevice_write_repository import update_renovation_only, update_checkability_only

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project'

class GUIWorkflowRegression(unittest.TestCase):
    def test_renovation_write_never_updates_checkability(self):
        db = Mock()
        update_renovation_only(db, 2030, 2, 'test', 123)
        sql, params = db.execute.call_args.args
        self.assertNotIn('nicht_pruefbar', sql)
        self.assertNotIn('grund_nicht_pruefbar', sql)
        self.assertEqual(params, (2030,2,'test',123))

    def test_checkability_write_never_updates_renovation(self):
        db = Mock()
        update_checkability_only(db, True, 'Nicht zugaenglich', 123)
        sql, params = db.execute.call_args.args
        self.assertNotIn('empfohlenes_sanierungsjahr', sql)
        self.assertNotIn('id_sanierungsart', sql)
        self.assertEqual(params, (True,'Nicht zugaenglich',123))

    def test_photo_is_context_bound(self):
        html = (ROOT / 'ui_templates/device_photo.html').read_text()
        self.assertIn('type="hidden" name="fid" value="{{ fid }}"',html)
        self.assertNotIn('type="number" name="fid"',html)

    def test_map_lazy_and_city_link(self):
        html = (ROOT / 'ui_templates/detail.html').read_text()
        self.assertIn('/device/map/', html)
        self.assertIn('stadtplan.winterthur.ch/mini?', html)
        self.assertIn('loading="lazy"',html)
