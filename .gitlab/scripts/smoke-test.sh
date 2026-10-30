#!/bin/sh
# Runs inside the application container: verify Django, API and native UI routing.
set -eu
python - <<'PY'
import json
import os
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener, urlopen

base = os.getenv('PLAYGROUND_BASE_PATH', '').strip().strip('/')
prefix = '/' + base if base else ''
origin = 'http://127.0.0.1:8010'

def get(path):
    with urlopen(origin + prefix + path, timeout=10) as response:
        assert response.status == 200, (path, response.status)
        return response.read(), response.headers

body, _ = get('/__django/health')
assert json.loads(body).get('backend') == 'django', 'Django WSGI is not active'
body, _ = get('/api/health')
assert json.loads(body).get('status') is not None, 'API health contract changed'
# A root request must redirect to the native UI. Do not follow the redirect:
# the protected destination is expected to require authentication.
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

try:
    build_opener(NoRedirect).open(origin + prefix + '/', timeout=10)
except HTTPError as exc:
    assert exc.code == 302, f'Unexpected root status: {exc.code}'
    assert exc.headers.get('Location') == prefix + '/__ui/', 'Root does not redirect to native UI'
else:
    raise AssertionError('Root must redirect to native UI')

body, _ = get('/__ui/login/')
assert b'<form' in body.lower(), 'Native login form is unavailable'
print('Smoke tests successful: Django WSGI, API health, native UI redirect and login')
PY
