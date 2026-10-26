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

### Native DRF-Authentifizierung (inkrementell)

Die geschuetzten DRF-Leseendpunkte nutzen jetzt `LegacyTokenAuthentication`
(`django_project/authentication.py`). Sie prueft Token und Datenbankbenutzer
ueber die unveraenderte `require_user`-Logik genau einmal pro Request.
Der Benutzer steht fuer spaetere DRF-Migrationen als `request.user` zur
Verfuegung. Die Authentifizierungsbruecke bewahrt bestehende Klartext-401-
Antworten. Oeffentliche Endpunkte, Login, Rollenpruefungen bei Legacy-Routen,
Datenbankschema, SMTP und TID-/FID-Regeln bleiben unveraendert.

### Native Berechtigungsprüfung (nächster Schritt)

Geschützte DRF-GET-Endpunkte verwenden `LegacyTokenAuthentication` zusammen
mit `IsLegacyAuthenticated`. Die Permission prüft das bereits einmalig
validierte Token-/Benutzerergebnis, ohne eine weitere Datenbankabfrage
anzustossen. Die spezifische Exception-Behandlung erhält bei Verweigerung
die ursprüngliche HTTP-Statuszahl, den Content-Type und den Klartext-Body.
Öffentliche DRF-Endpunkte bleiben explizit ohne Authentifizierung und Permission.
Rollenabhängige fachliche Filter bleiben weiterhin in der Fachlogik; native
rollenbezogene Permissions kommen erst mit entsprechenden geschützten
Schreib-Endpunkten hinzu. Weder Login noch TID-/FID-Vergabe wurden verändert.


### Schritt 7 – erste fachliche Modularisierung

`playground_reads.py` enthält HTTP- und datenbankunabhängige Transformationen der
Spielplatz-Leseantworten (GeoJSON und Inspektionssistierung). Die bisherigen
Namen `_public_feature` und `_suspended` bleiben in `service.py` als
Import-Aliase erhalten, sodass die bestehenden Aufrufstellen kompatibel bleiben.
Neue DRF-Views importieren die GeoJSON-Transformation direkt aus dem Fachmodul.
Weitere Datenbankabfragen und sämtliche Schreiboperationen bleiben unverändert.

### Schritt 8 – Detailantworten fachlich modularisieren

`playground_detail_serializers.py` enthält reine Transformationen für
Inspektionsberichte (`report_dict`), Prüfkriterien (`criterion_dict`) und
Spielgeräte-GeoJSON (`playdevice_feature`). SQL-Zugriffe und die Zusammenstellung
der Daten verbleiben in `service.py`; die dortigen `_report_dict`- und
`_criterion_dict`-Namen bleiben als kompatible Aliase erhalten.

Die Testfälle sichern Standardwerte, Datenfelder und die Ausgabe bei fehlenden
Inspektionsdaten ab. Endpunkte, Authentifizierung, SMTP, Schreibvorgänge und
FID-/TID-Vergabe bleiben unverändert.

### Schritt 9 – Repository-Schicht für Spielplatzdetails

`playground_repository.py` übernimmt drei lesende PostgreSQL-Abfragen:
Spielplatz nach Name, Spielplatz über bestehende Spielgeräte-FID und die
Spielgerätezeilen eines Spielplatzes. Die bestehenden SQL-Statements und
Parameterbindungen bleiben unverändert. Die Verbindung und ihre Lebensdauer
verbleiben beim aufrufenden Service. Die bisherige Funktion `_playdevice_rows`
ist als delegierender Wrapper erhalten. Keine Schemaänderungen, keine neuen
FID-/TID-Werte und keine Änderungen an Schreib-Endpunkten.

### Schritt 10 – Inspektions- und Mangel-Repository

Lesende SQL-Abfragen fuer Pruefkriterien, Inspektionsberichte und Maengel liegen
neu in `inspection_defect_repository.py`. Die Service-Funktionen uebernehmen
weiterhin die fachliche Datenaufbereitung. Die Datenbankverbindung wird vom
Aufrufer uebergeben; SQL und Parameterbindung bleiben unveraendert. Zugelassene
View-/Spaltenkombinationen der Pruefkriterien sind explizit festgelegt.
Schreiboperationen, TID-/FID-Vergabe und SMTP bleiben unveraendert.

## Schritt 11: Detail-Service

Die lesende Zusammenstellung des Spielplatz-Detailpayloads liegt neu in
`playground_detail_service.build_playground_detail`. Die alte
`service._playground_result`-Signatur bleibt als kompatibler Delegator erhalten.
Datenbankverbindung, SQL-Texte, Dokument-Metadaten und bestehende FIDs werden
unverändert weiterverwendet. Es gibt keine neuen Schreiboperationen.
