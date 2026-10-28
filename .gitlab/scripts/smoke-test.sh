#!/bin/sh
# Runs *inside* the application container: verify Django/DRF and legacy SPA.
set -eu
python - <<'PY'
import json
import os
from urllib.request import urlopen

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
body, headers = get('/')
assert b'Spielplatzkontrolle' in body, 'Legacy SPA unavailable'
print('Smoke tests successful: Django WSGI, API health, SPA')
PY
