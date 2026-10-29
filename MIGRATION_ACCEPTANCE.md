# Spielplatzkontrolle – Migrationsabnahme (29. Oktober 2026)

## Status

The functional API routes in `server.create_router()` are all mapped by the
method-aware Django dispatcher. The Django / DRF service is the WSGI entrypoint.
**This does not mean that the legacy Python request/response architecture has
been completely removed.** Several DRF command modules still deliberately use
`legacy_adapter` for faithful binary and error responses; `server.Application`
remains the fallback for the SPA, static resources, Swagger UI, invalid methods
and unmatched paths. These dependencies must remain until byte-level parity is
verified. Do not delete the WSGI fallback or compatibility adapter solely on
the strength of the route audit.

## Local release gate

1. Apply each patch in ascending order (40c, 40d, 42) on top of the working
   step 40b, checking `git apply --check` before each application.
2. Install project requirements including `.[django]` in the approved venv.
3. Run `sh tools/verify_migration.sh`. A test skipped because of missing
   dependencies is **not** an acceptance pass.
4. For the integration test, use an isolated PostgreSQL/PostGIS DB and set
   `PLAYGROUND_TEST_POSTGRES_DSN` and
   `PLAYGROUND_TEST_DATABASE_CONFIRMED=isolated-test-only`. Never point these
   variables at a production or shared database.
5. Compare auth errors, role checks, TID generation, FID integrity, dryRun,
   binary image/PDF MIME types and bytes, email transaction ordering and SMTP
   failures against the previous system.
6. On `wsstadt723`, validate the Docker image, Gunicorn WSGI entrypoint,
   reverse proxy base `/stadtgruen/spielplatzkontrolle/`, SPA/deep links,
   Swagger, static assets, service worker and health endpoints.
7. Check GitLab pipeline and rehearse rollback before production approval.

## Release decision

- Route coverage: automated, `python tools/check_api_routes.py`.
- Python syntax and regression tests: automated in verification script.
- Integration, live reverse proxy, CI pipeline and rollback: **requires
  operator validation in the target environment**.
- Complete elimination of legacy compatibility layers: **not yet achieved**.

Release only after every required gate has passed and the remaining adapters
are explicitly accepted as technical debt or separately replaced with tested
native equivalents.

## Explicit remaining work before a native-only claim

The patch consolidates steps 40c, 40d and 42, plus a static legacy dependency
inventory. It does **not** replace compatibility-dependent database, security,
image, mail or service behaviors without contract parity tests. To obtain an
up-to-date, source-based list of import sites, run:

```sh
python tools/check_migration_dependencies.py
python tools/check_migration_dependencies.py --require-native
```

The second command intentionally exits nonzero until all direct imports of
`legacy_adapter`, `playground_check.service` and `playground_check.server` from
Django modules have been eliminated. The WSGI frontend/Swagger fallback is
also still present and requires separate acceptance. An API route coverage
pass must not be interpreted as full architectural independence.
