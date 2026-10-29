# Legacy endpoint inventory – step 40 (29 October 2026)

Source of truth: `server.create_router()`, `django_project.route_registry.ROUTES`,
`django_project.urls.urlpatterns` and `django_project.wsgi.application`.

## Still dispatched to the legacy WSGI application

| Method | Legacy path | Reason / follow-up |
| --- | --- | --- |
| GET | `/Playground/{invalid_id}` | Unconstrained ASP.NET-style model-binding validation, including malformed numeric IDs; preserve HTTP 400 JSON envelope |
| Other/unmatched | All legacy router paths | Method-sensitive fallback preserves HTTP 405, `Allow`, 404 and malformed requests |
| GET | `/swagger`, `/swagger/index.html`, `/swagger/v1/swagger.json` | Legacy-generated Swagger UI and OpenAPI document |
| GET | `/static/*`, SPA routes and deep links | Frontend resources, CSP nonce, `sw.js`, history fallback, base-path behavior |

`GET /Playground/{numeric_id}` and `GET /Playground/mapimage` were moved to DRF in steps 40a and 40b respectively (with
`compatibility_bugs` behavior and authorization preserved). Other routes
registered in `server.create_router()` have entries in the DRF method-aware
registry; **this does not prove they are fully free of legacy service helpers**.

## Remaining architectural dependencies

- `django_project.views` imports `service` read helpers, including
  `playground_by_name_data`, `playground_only_names_data`,
  `playground_by_device_data` and now `playground_by_id_data`.
- `django_project.authentication` uses `service.require_user`, preserving
  authorization against the existing identity model.
- `django_project.legacy_adapter` remains available for incremental migration.
  Verify actual import sites before considering its removal.
- Legacy `server.Application` still owns the SPA, static assets, Swagger,
  generic HTTP fallback, and unmatched requests. Do not remove it yet.

## Required checks before further removal

1. Compare method/path pairs and response bytes against the legacy application.
2. Verify numeric ID lookup with `compatibility_bugs` both enabled and disabled.
3. Verify unauthorized HTTP 401 body and correct query flags.
4. Verify malformed ID HTTP 400 via fallback, GET/POST HTTP 405 semantics.
5. Exercise `/stadtgruen/spielplatzkontrolle/` reverse-proxy path base, SPA
   deep links, Swagger and static files in the deployed test environment.
6. Run the full regression suite and isolated PostgreSQL integration tests;
   never run write integration tests on the production database.

## Step 40b – Map image

`GET /Playground/mapimage` now uses a public DRF view, with a shared WMS
helper (`map_image_queries.py`) reused by the legacy service. Its response is
a JSON string containing base64 of the upstream response bytes, not a PNG
response. The HTTPError body is also encoded as before, and missing or zero
coordinates avoid the WMS request. No WMS network calls are made in tests.

Remaining legacy responsibilities are malformed IDs, unmatched methods,
Swagger/OpenAPI, SPA/static resources and generic fallbacks.
