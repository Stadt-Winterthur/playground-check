"""Multipart, Base64 compatibility and byte boundaries through real DRF routes."""
import base64
import json
import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.test import Client, RequestFactory
from django.test.client import encode_multipart, BOUNDARY, MULTIPART_CONTENT
from playground_check import domain_support
from playground_check.upload_limits import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES, UPLOAD_REQUEST_MAX_BYTES
from playground_check.django_project import document_commands, python_ui, python_ui_workflows
from playground_check.django_project.uploads import UploadLimitMiddleware, read_file, UploadTooLarge


def pdf(size):
    return b'%PDF-1.4\n' + b' ' * (size - 9)


def png(size):
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * (size - 8)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        user = {'fid': 17, 'role': 'administrator', 'mailAddress': 'test@example.invalid'}
        self.stack.enter_context(patch.object(domain_support, 'require_user', return_value=(user, None)))
        self.stack.enter_context(patch.object(python_ui, 'require_user', return_value=(user, None)))
        db = MagicMock(); db.__enter__.return_value = db
        self.db = db
        self.stack.enter_context(patch.object(domain_support, 'connect', return_value=db))
        self.doc = self.stack.enter_context(patch.object(domain_support.document_write_repository, 'insert_document', return_value=99))
        self.image = self.stack.enter_context(patch.object(domain_support.picture_write_repository, 'update_playdevice_picture'))
        self.defect = self.stack.enter_context(patch.object(domain_support.picture_write_repository, 'insert_defect_picture', return_value={'tid': 123}))
        self.client = Client(raise_request_exception=False)

    def post_pdf(self, content):
        return self.client.post('/Document/', {
            'type': 'abnahme', 'name': 'Test', 'playgroundId': '42',
            'document': SimpleUploadedFile('test.pdf', content, content_type='application/pdf')})

    def test_exact_20_mib_multipart_pdf_is_spooled_and_saved(self):
        original = document_commands.pdf_file
        spooled = []
        def read(upload):
            spooled.append(isinstance(upload, TemporaryUploadedFile))
            return original(upload)
        with patch.object(document_commands, 'pdf_file', side_effect=read):
            response = self.post_pdf(pdf(DOCUMENT_MAX_BYTES))
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(spooled, [True])
        stored, _ = domain_support._document_parts(self.doc.call_args.args[-1])
        self.assertEqual(len(stored), DOCUMENT_MAX_BYTES)

    def test_pdf_one_byte_over_limit_is_413_without_write(self):
        response = self.post_pdf(pdf(DOCUMENT_MAX_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        self.doc.assert_not_called()

    def test_base64_pdf_over_old_django_limit_is_still_supported(self):
        content = pdf(3 * 1024 * 1024)
        response = self.client.post('/Document/', json.dumps({
            'type': 'abnahme', 'name': 'Test', 'playgroundId': 42,
            'contentBase64': base64.b64encode(content).decode()}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content[:200])
        stored, _ = domain_support._document_parts(self.doc.call_args.args[-1])
        self.assertEqual(stored, content)

    def test_base64_pdf_above_decoded_limit_is_413(self):
        response = self.client.post('/Document/', json.dumps({
            'type': 'abnahme', 'name': 'Test', 'playgroundId': 42,
            'contentBase64': base64.b64encode(pdf(DOCUMENT_MAX_BYTES + 1)).decode()}), content_type='application/json')
        self.assertEqual(response.status_code, 413)
        self.doc.assert_not_called()

    def test_multipart_put_accepts_10_mib_device_picture(self):
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(IMAGE_MAX_BYTES))})
        response = self.client.put('/Playdevice/42/Picture/', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 200, response.content[:200])
        raw, mime = domain_support._decode_image(self.image.call_args.args[-1])
        self.assertEqual((len(raw), mime), (IMAGE_MAX_BYTES, 'image/png'))

    def test_multipart_image_over_limit_does_not_write(self):
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(IMAGE_MAX_BYTES + 1))})
        response = self.client.put('/Playdevice/?fid=42', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 413)
        self.image.assert_not_called()

    def test_multipart_defect_photo_keeps_storage_format_and_after_flag(self):
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(32)), 'afterFixing': 'true'})
        response = self.client.put('/Defect/Picture/42/', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 200, response.content[:200])
        args = self.defect.call_args.args
        self.assertEqual(args[1], 42)
        self.assertEqual(domain_support._decode_image(args[2])[0], png(32))
        self.assertEqual(args[2], args[3])
        self.assertTrue(args[4])

    def test_after_photo_rejected_for_open_defect_without_insert(self):
        self.db.execute.return_value.fetchone.return_value = {'done_by': None}
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(32)), 'afterFixing': 'true'})
        response = self.client.put('/Defect/Picture/42/', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 409)
        self.defect.assert_not_called()

    def test_after_photo_accepted_for_completed_defect(self):
        self.db.execute.return_value.fetchone.return_value = {'done_by': 17}
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(32)), 'afterFixing': 'true'})
        response = self.client.put('/Defect/Picture/42/', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 200)
        self.defect.assert_called_once()

    def test_after_photo_rejected_for_missing_defect(self):
        self.db.execute.return_value.fetchone.return_value = None
        body = encode_multipart(BOUNDARY, {'picture': SimpleUploadedFile('test.png', png(32)), 'afterFixing': 'true'})
        response = self.client.put('/Defect/Picture/42/', body, content_type=MULTIPART_CONTENT)
        self.assertEqual(response.status_code, 404)
        self.defect.assert_not_called()

    def test_invalid_missing_duplicate_or_unexpected_files_do_not_write(self):
        for data in ({'document': SimpleUploadedFile('test.pdf', b'not a pdf')}, {},
                     {'document': [SimpleUploadedFile('a.pdf', pdf(20)), SimpleUploadedFile('b.pdf', pdf(20))]},
                     {'other': SimpleUploadedFile('test.pdf', pdf(20))}):
            with self.subTest(keys=list(data)):
                response = self.client.post('/Document/', {'type': 'abnahme', 'name': 'Test', 'playgroundId': '42', **data})
                self.assertEqual(response.status_code, 400)
        self.doc.assert_not_called()

    def test_html_document_form_passes_file_without_json_adapter(self):
        with patch.object(python_ui_workflows, '_native', side_effect=AssertionError('JSON adapter used')):
            response = self.client.post('/document/upload/', {'type': 'abnahme', 'name': 'Test', 'playgroundId': '42',
                'document': SimpleUploadedFile('test.pdf', pdf(3 * 1024 * 1024))})
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.doc.assert_called_once()

    def test_html_device_photo_uses_parsed_file_without_raw_body_read(self):
        response = self.client.post('/device/photo/', {'fid': '42', 'name': 'Test',
            'picture': SimpleUploadedFile('test.png', png(32))})
        self.assertEqual(response.status_code, 303, response.content[:200])
        self.image.assert_called_once()

    def test_limits_match_application_and_django(self):
        # The reverse proxy is configured outside this application repository.
        # Verify the application contract without depending on a deployment snippet.
        self.assertEqual(UPLOAD_REQUEST_MAX_BYTES, 32 * 1024 * 1024)
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, UPLOAD_REQUEST_MAX_BYTES)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 1024 * 1024)

    def test_oversized_request_is_rejected_before_parsing(self):
        next_view = MagicMock()
        request = RequestFactory().post('/Document/', b'', content_type='application/json')
        request.META['CONTENT_LENGTH'] = str(UPLOAD_REQUEST_MAX_BYTES + 1)
        response = UploadLimitMiddleware(next_view)(request)
        self.assertEqual(response.status_code, 413)
        next_view.assert_not_called()

    def test_bounded_reader_checks_actual_length_as_well_as_declared_size(self):
        upload = MagicMock(size=1)
        upload.read.return_value = b'12345'
        with self.assertRaises(UploadTooLarge):
            read_file(upload, 4)
        upload.read.assert_called_once_with(5)
