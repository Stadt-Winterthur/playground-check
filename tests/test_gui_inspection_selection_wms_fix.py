"""Protect CSP-compatible inspection choices and WMS fallback."""
import base64
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from django.test import RequestFactory
from playground_check.django_project import python_ui_workflows as workflows


class InspectionSelectionWMSFixTests(unittest.TestCase):
    def test_wms_fallback_after_nonimage_response(self):
        png = b"\x89PNG\r\n\x1a\n" + b"sample"
        calls = []
        def fetch(params, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return base64.b64encode(b"403 Forbidden").decode()
            return base64.b64encode(png).decode()
        request = RequestFactory().get("/__ui/device/map/?x=2700212&y=1262696")
        with patch.object(workflows, "_guard", return_value=({"role": "inspector"}, None)), \
             patch.object(workflows, "settings", SimpleNamespace(wms_url="http://stadtplantest.winterthur.ch/wms/")), \
             patch("playground_check.map_image_queries.map_image_base64", side_effect=fetch):
            response = workflows.playdevice_map(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, png)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["endpoint_override"], "https://stadtplan.winterthur.ch/wms/Spielplatzkarte")
