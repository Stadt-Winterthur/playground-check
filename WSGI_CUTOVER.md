# Django-only WSGI cutover

The deployment WSGI entry point no longer invokes `server.application`. All HTTP requests enter Django. The route registry canonicalizes known API paths independently of HTTP method so Django/DRF can decide whether to return HTTP 405; unmatched API paths receive Django frontend's 404 handling. `server.py` remains in the repository solely to preserve separate historical comparison tests.

Validate status, body, headers, cookie and content type against the previous deployment for malformed URLs, unsupported methods, unauthenticated clients and reverse-proxy prefixed paths. In particular, the former legacy WSGI router may have returned 401 for some unknown API routes, while Django now returns 404. This intentional architectural change requires explicit client acceptance. PostgreSQL integration and a test-server deployment remain required before production use.
