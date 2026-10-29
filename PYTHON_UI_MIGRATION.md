# Python UI migration: isolated preview, not complete

`/__ui/` serves a Django-rendered entry page and `/__ui/playgrounds/`
serves a read-only searchable public playground list. Existing SPA and
all write workflows remain unchanged. The current implementation does **not**
include HTMX interactions; this is a Python/Django preview, not a complete
Django Templates + HTMX migration.

Not yet migrated: authentication, inspection forms, defects, play devices,
image/document operations, users, notifications, offline/browser state.
The old `app.js` must not be removed until these are implemented and tested.
