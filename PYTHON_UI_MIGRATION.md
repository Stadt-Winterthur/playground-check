# Python-first GUI migration - authenticated read workflows

This patch adds a real server-rendered Django template UI with navigation,
public search, authenticated workspace, user-specific playground selection,
playground details and device/defect summaries. It retains the existing DRF
endpoints and the production SPA without changing any write behavior.

**Not yet a complete replacement.** Editing inspections, defect workflows,
photo/document uploads, users, offline queues and push notifications still need
full parity implementation and browser acceptance tests.

HTMX-compatible fragment endpoints (HX-Request) and hx attributes are included,
but the browser enhancement is **inactive** until an approved local htmx JS
bundle is provided. Ordinary GET forms and navigation work without JS.

Test with `python -m unittest discover -s tests -v`; PostgreSQL integration
requires `PLAYGROUND_TEST_POSTGRES_DSN`. The original frontend remains at `/`.

## Nächster Fachbereich: Mängelübersicht

Unter `/__ui/defects/` ist eine geschützte, lesende Mängelübersicht verfügbar. Sie verwendet `remaining_reads_repository.defect_overview_rows`, filtert nach Status und Suchtext und begrenzt die Ausgabe auf 30 Datensätze je Seite. Bearbeitung und Offline-Synchronisierung bleiben in der bestehenden GUI. HTMX-Attribute sind vorbereitet, aber ohne lokal eingebundene HTMX-JavaScript-Bibliothek erfolgt die Suche mit normalem GET-Formular.
