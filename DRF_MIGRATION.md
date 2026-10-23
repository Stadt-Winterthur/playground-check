# Schritt 3 – erste API-Endpunkte mit Django REST Framework

Die Nutzung ist weiterhin **opt-in** über `playground_check.django_project.wsgi:application`.
Der bisherige produktive WSGI-Einstiegspunkt bleibt unverändert.

Native DRF-GET-Routen: `/api/health`, `/__django/health`,
`/Collections/Playgrounds/Items/` (inklusive optionalem `PathBase`).
Alle anderen Routen und Schreibmethoden werden weiterhin an die bisherige WSGI-Anwendung delegiert.

Die öffentliche Spielplatzsammlung nutzt vorläufig weiterhin die vorhandene SQL-Abfrage
und den GeoJSON-Mapper. Es gibt **keine** Änderung an Datenbank, TID-/FID-Vergabe,
Authentifizierung und Frontend. Das historisch bestehende Fehlerformat (HTTP 200
mit Fehler-Feature) wird zur Wahrung des API-Vertrags beibehalten.

Installation: `python -m pip install -e '.[django]'`.
Tests: `python -m unittest discover -s tests -v`.
Optionale lokale Ausführung: `gunicorn --bind 127.0.0.1:8011 playground_check.django_project.wsgi:application`.

Weitere API-Endpunkte werden erst nach kontraktgleichen Tests umgestellt.

## Weiterer Schritt: geschützte Auswahllisten

- `GET /Inspection/types/` und `GET /Inspection/renovationtypes/` werden über DRF abgewickelt.
- Authentifizierung und Autorisierung laufen weiterhin über `service.require_user` einschließlich DB-Abgleich und `dryRun`-Verhalten.
- Erfolgsantworten, HTTP-401-Textantworten und SQL-Abfragen bleiben kompatibel.
- Sonstige Methoden bleiben an den Legacy-Handler delegiert.
- Schreiboperationen und TID/FID-Vergabe bleiben unberührt.
