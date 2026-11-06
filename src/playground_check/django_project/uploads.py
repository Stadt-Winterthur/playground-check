"""Bounded multipart reads; only database-compatible image storage is Base64."""
import base64
from django.http import JsonResponse
from rest_framework.exceptions import APIException, ParseError
from playground_check import domain_support as service
from playground_check.upload_limits import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES, UPLOAD_REQUEST_MAX_BYTES


class UploadTooLarge(APIException):
    status_code = 413
    default_detail = {'errorMessage': 'Datei oder Anfrage ist zu gross.'}


def is_multipart(request):
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    return content_type.split(';', 1)[0].strip().lower() == 'multipart/form-data'


def multipart_parts(request, allowed_files):
    # DRF parses multipart PUT as well as POST; plain Django handles HTML POST.
    data = request.data if hasattr(request, '_request') else request.POST
    files = request.FILES
    if any(key not in allowed_files for key in files):
        raise ParseError({'errorMessage': 'Unerwartete Datei.'})
    if hasattr(files, 'getlist') and any(len(files.getlist(key)) != 1 for key in files):
        raise ParseError({'errorMessage': 'Pro Dateifeld ist nur eine Datei erlaubt.'})
    return data, files


def read_file(upload, maximum):
    if upload is None or upload.size == 0:
        raise ParseError({'errorMessage': 'Datei fehlt.'})
    if upload.size > maximum:
        raise UploadTooLarge()
    content = upload.read(maximum + 1)
    if len(content) > maximum:
        raise UploadTooLarge()
    return content


def pdf_file(upload):
    content = read_file(upload, DOCUMENT_MAX_BYTES)
    if not content.startswith(b'%PDF-'):
        raise ParseError({'errorMessage': 'Nur PDF-Dateien erlaubt.'})
    return content


def image_file(upload):
    content = read_file(upload, IMAGE_MAX_BYTES)
    mime = service._mime(content)
    if mime not in service.ALLOWED_IMAGE_MIME_TYPES:
        raise ParseError({'errorMessage': 'Nicht unterstützter Bildtyp.'})
    return 'data:' + mime + ';base64,' + base64.b64encode(content).decode('ascii')


class UploadLimitMiddleware:
    """Reject declared oversized requests before Django/CSRF parses uploads.

    The proxy limit is still required, including for chunked upstream bodies.
    File reads and Django's JSON body limit provide additional bounded checks.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0)
        except (ValueError, TypeError):
            return JsonResponse({'errorMessage': 'Ungültige Anfragelänge.'}, status=400)
        if length < 0:
            return JsonResponse({'errorMessage': 'Ungültige Anfragelänge.'}, status=400)
        if length > UPLOAD_REQUEST_MAX_BYTES:
            return JsonResponse({'errorMessage': 'Datei oder Anfrage ist zu gross.'}, status=413)
        return self.get_response(request)
