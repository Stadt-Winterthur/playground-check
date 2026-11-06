#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c "import psycopg, dotenv, django, rest_framework, gunicorn" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -e ".[django,production]"
fi
exec .venv/bin/gunicorn --bind "${PLAYGROUND_HOST:-127.0.0.1}:${PLAYGROUND_PORT:-8010}" --workers 1 --threads 4 --access-logfile - --error-logfile - playground_check.django_project.wsgi:application
