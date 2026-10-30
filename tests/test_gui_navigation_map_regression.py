"""Protect inspection-start UI, photo roundtrips, and WMS failure semantics."""
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory
from playground_check.django_project import python_ui, python_ui_workflows


class NavigationMapRegression(unittest.TestCase):
    def test_general_detail_never_shows_inspection_start(self):
        factory = RequestFactory()
        req = factory.get('/__ui/detail/?name=Test')
        payload = {'name': 'Test', 'playdevices': [], 'inspectionTypeOptions': ['Visuelle Inspektion (VI)']}
        with patch.object(python_ui, '_private', return_value=({'role': 'inspector', 'mailAddress': 'x@y.ch'}, None)), \
             patch.object(python_ui, 'playground_by_name_data', return_value=payload), \
             patch.object(python_ui, 'playground_only_names_data') as lookup:
            result = python_ui.playground_detail(req)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(b'Inspektion starten', result.content)
        lookup.assert_not_called()

    def test_only_assigned_inspection_type_has_start(self):
        factory = RequestFactory()
        req = factory.get('/__ui/detail/?name=Test&inspectiontype=Visuelle%20Inspektion')
        payload = {'name': 'Test', 'playdevices': [], 'inspectionTypeOptions': ['Visuelle Inspektion (VI)']}
        with patch.object(python_ui, '_private', return_value=({'role': 'inspector'}, None)), \
             patch.object(python_ui, 'playground_by_name_data', return_value=payload), \
             patch.object(python_ui, 'playground_only_names_data', return_value=[{'name': 'Andere'}]):
            result = python_ui.playground_detail(req)
        self.assertNotIn(b'Inspektion starten', result.content)

    def test_wrong_wms_data_returns_gateway_error_not_not_found(self):
        req = RequestFactory().get('/__ui/device/map/?x=2700212&y=1262696')
        with patch.object(python_ui_workflows, '_guard', return_value=({'role': 'inspector'}, None)), \
             patch('playground_check.map_image_queries.map_image_base64', return_value='PGh0bWw+NDAzPC9odG1sPg=='):
            res = python_ui_workflows.playdevice_map(req)
        self.assertEqual(res.status_code, 502)

    def test_photo_context_is_preserved(self):
        template = (Path(python_ui.TEMPLATE_ROOT) / 'device_photo.html').read_text()
        self.assertIn('name="name"', template)
        self.assertIn('name="inspectiontype"', template)
