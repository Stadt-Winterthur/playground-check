"""Django-only browser entry, static resources and API documentation.

Legacy SPA routes are redirected to native pages; no legacy HTML is served.
"""
from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote, urlencode

from django.http import HttpResponse, HttpResponseRedirect

from playground_check.config import settings
from playground_check.openapi import build_openapi_document, swagger_ui_html

_STATIC = Path(__file__).resolve().parent.parent / 'static'
_API_PREFIXES = frozenset({
    'account', 'inspection', 'collections', 'playground', 'playdevice',
    'defect', 'document', 'pushsubscription', 'swagger', 'api',
})


def frontend(request, path: str = ''):
    """Static assets, Swagger and safe redirects; unknown URLs return 404."""
    route = '/' + path.lstrip('/')
    prefix = (request.META.get('SCRIPT_NAME') or settings.base_path or '').rstrip('/')
    if route in ('/swagger', '/swagger/'):
        response = HttpResponseRedirect(prefix + '/swagger/index.html')
        return response
    if route == '/swagger/index.html':
        return HttpResponse(swagger_ui_html(prefix), content_type='text/html; charset=utf-8')
    if route == '/swagger/v1/swagger.json':
        return HttpResponse(json.dumps(build_openapi_document(), ensure_ascii=False, separators=(',', ':')),
                            content_type='application/json; charset=utf-8')
    if route.startswith('/static/'):
        target = (_STATIC / route[len('/static/'):]).resolve()
        if _STATIC.resolve() not in target.parents or not target.is_file():
            return HttpResponse('Not found', status=404, content_type='text/plain; charset=utf-8')
        content_type = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        response = HttpResponse(target.read_bytes(), content_type=content_type)
        if route == '/static/sw.js':
            response['Service-Worker-Allowed'] = prefix + '/'
            response['Cache-Control'] = 'no-cache'
        return response
    if request.method != 'GET':
        return HttpResponse('Not found', status=404, content_type='text/plain; charset=utf-8')

    # Old bookmarks and push notification deep links must reach native pages.
    redirect_to = None
    defect = re.fullmatch(r'/defect/\d+/(\d+)/?', route, re.IGNORECASE)
    if defect:
        redirect_to = '/defect/?' + urlencode({'tid': defect.group(1)})
    elif route in ('/users', '/users/'):
        redirect_to = '/admin/users/' if route.rstrip('/') == '/users' else '/'
    elif route.rstrip('/') in ('/defects', '/assigned', '/inspections', '/playdevices', '/playgrounds'):
        redirect_to = {
            '/defects': '/defects/',
            '/assigned': '/assigned/',
            '/inspections': '/assigned/?mode=inspection',
            '/playdevices': '/assigned/',
            '/playgrounds': '/assigned/',
        }[route.rstrip('/')]
    else:
        detail = re.fullmatch(r'/deviceattributes/playdevice/(\d+)/?', route, re.IGNORECASE)
        if detail:
            redirect_to = '/device/edit/?' + urlencode({'fid': detail.group(1)})
    if redirect_to is not None:
        response = HttpResponseRedirect(prefix + redirect_to)
        response['Cache-Control'] = 'no-store'
        return response
    if route.lstrip('/').split('/', 1)[0].casefold() in _API_PREFIXES:
        return HttpResponse('Not found', status=404, content_type='text/plain; charset=utf-8')
    return HttpResponse('Not found', status=404, content_type='text/plain; charset=utf-8')
