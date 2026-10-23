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

### Spielplatzdetails (nächste Etappe)

- `GET /Collections/Playgrounds/Items/<uuid>/` wird über DRF ausgeliefert. Das bisherige GeoJSON einschliesslich der Fehlerobjekte bleibt erhalten.
- `GET /Playground/byname/` wird über DRF ausgeliefert. Die bestehende Token-/Benutzerprüfung bleibt aktiv; die Detailaufbereitung ist als `playground_by_name_data(query)` von der HTTP-Antwort getrennt und wird von Legacy und DRF gemeinsam genutzt.
- Andere Spielplatzrouten und alle Schreiboperationen verbleiben in der bisherigen WSGI-App. Insbesondere `GET /Playground/<id>/` wird wegen des dokumentierten Legacy-Kompatibilitätsverhaltens noch nicht migriert.
- Keine Änderungen an PostgreSQL-Schema, TID-/FID-Vergabe oder dem SMTP-Mailversand.

### Weitere geschützte Spielplatz-Leseoperationen

- `GET /Playground/onlynames/` und `GET /Playground/byplaydevice/<fid>/` laufen über DRF.
- Die SQL- und Antwortlogik liegt in gemeinsam genutzten Funktionen in `service.py`.
- Token-/Benutzerkontrolle, die nach Benutzer gefilterte Namensliste und Antworten für fehlende Geräte bleiben erhalten.
- `GET /Playground/<id>/` bleibt vorerst Legacy: Der bewusst erhaltene Kompatibilitätsfehler wird nicht stillschweigend geändert.
- Schreiboperationen, SMTP-Versand und TID-/FID-Vergabe bleiben unverändert.

### Einheitliche Authentifizierungsbrücke (nächster Schritt)

`django_project/access.py` bündelt die Übergabe von DRF-Requests an die
bestehende `require_user`-Prüfung. Bestehende Bearer-Token, Benutzerabgleich
mit PostgreSQL und bisherige Klartext-Fehlerantworten bleiben unverändert.
Eine Umstellung auf native DRF-Authentifizierung erfolgt erst separat und
mit passenden Vergleichstests; es werden keine Django-User-Tabellen angelegt.
