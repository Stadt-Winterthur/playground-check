# Django migration – stage 2: opt-in entry point

This is a **parallel migration scaffold**, not a completed Django port. The existing
WSGI application, including business logic, API, static files and frontend, remains
unchanged. The existing `playground-check` command and Dockerfile still use the
legacy entry point. No migrations or database writes are involved.

## Installation / local smoke test

```bash
python -m pip install -e '.[django]'
python -m unittest discover -s tests -v
# Optional: start the Django-first WSGI router using gunicorn:
python -m pip install gunicorn
gunicorn --bind 127.0.0.1:8011 playground_check.django_project.wsgi:application
```

Then check `/__django/health` (new Django endpoint), `/api/health`
(unchanged legacy response), and the existing frontend.

`PLAYGROUND_SECURITY_KEY` must be configured as before; this is also used
as the initial Django SECRET_KEY. The Django health route is deliberately
not a replacement for `/api/health`.

The existing `PLAYGROUND_BASE_PATH` setting is respected by the WSGI router.
No reverse proxy changes are required while the original entry point is used.

## Next migration slices

Move one read-only endpoint into Django first, preserving HTTP method, path,
status, response JSON and permissions. Add parity tests before switching
production to the opt-in router. Then migrate write endpoints in small
steps, preserving the Oracle-master FID / web-app TID contract.

**Important:** ALLOWED_HOSTS is permissive in this isolated scaffold and
needs production host configuration before switching public traffic to Django.
