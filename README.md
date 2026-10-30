# Spielplatzkontrolle

Webanwendung für die Kontrolle und Mängelbearbeitung der Winterthurer Spielplätze. Frontend und Python-Backend befinden sich im selben Repository und greifen direkt auf die bestehende PostgreSQL-/PostGIS-Datenbank zu.

## Funktionen

- Anmeldung und rollenbasierter Zugriff
- Spielplätze, Spielgeräte, Fotos, Dokumente und Karte
- visuelle, operative und Hauptinspektionen
- Erfassung und Bearbeitung von Mängeln inkl. Zuständigkeit, Priorität, Status und Fotos
- Zuweisung, Annahme und Ablehnung von Mängeln
- Benutzerverwaltung
- EML-Erzeugung für Mangelmeldungen
- optionale ELK-Protokollierung und Push-Subscription-API

## Voraussetzungen

- Python 3.11 oder neuer für den lokalen Betrieb
- PostgreSQL mit PostGIS und dem benötigten Anwendungsschema
- für Produktion: Docker Engine mit Docker-Compose-Plugin und ein TLS-Reverse-Proxy

Der Datenbankbenutzer benötigt Lese- und Schreibrechte auf den von der Anwendung verwendeten Tabellen und Views. Mit folgendem Befehl kann die Datenbank geprüft werden:

```sh
python -m playground_check --check-database
```

## Lokaler Start

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[django,production]"
cp .env.example .env
```

Danach `.env` (insbesondere Datenbank, Security-Key und Salt) anpassen und die Django-Anwendung starten:

```sh
./start.sh
```

Lokale URL: `http://127.0.0.1:8010/__ui/` (bei gesetztem `PLAYGROUND_BASE_PATH` mit diesem Präfix). `start.sh` startet Gunicorn mit `playground_check.django_project.wsgi:application`; `python -m playground_check` startet weiterhin den alten Server und ist für die neue Oberfläche ungeeignet.

## Konfiguration

Die Anwendung liest `.env` aus dem Projektverzeichnis. Bereits gesetzte Umgebungsvariablen haben Vorrang.

Wichtige Variablen:

| Variable | Bedeutung |
|---|---|
| `PLAYGROUND_POSTGRES_DSN` | PostgreSQL-Verbindung |
| `PLAYGROUND_SECURITY_KEY` | JWT-Signaturschlüssel, mindestens 32 Zeichen |
| `PLAYGROUND_SALT_BASE64` | Base64-Salt für die vorhandenen Passwort-Hashes |
| `PLAYGROUND_SERVICE_URL` | öffentliche Basis-URL der Anwendung |
| `PLAYGROUND_BASE_PATH` | optionaler URL-Unterpfad |
| `PLAYGROUND_WMS_URL` | WMS-Adresse für die Kartenansicht |
| `PLAYGROUND_TITLE` | Titel der Webanwendung |
| `PLAYGROUND_SERVICE_WORKER_ENABLED` | Service Worker aktivieren/deaktivieren |

`PLAYGROUND_SALT_BASE64` muss zu den vorhandenen Passwort-Hashes in `wgr_sp_kontrolleur` passen. Ein ungültiger Base64-Wert verhindert den Start der Anwendung.

## Produktion mit Docker Compose

Produktive Konfiguration anlegen:

```sh
cp .env.production.example .env
chmod 600 .env
```

Mindestens `PLAYGROUND_POSTGRES_DSN`, `PLAYGROUND_SECURITY_KEY`, `PLAYGROUND_SALT_BASE64` und `PLAYGROUND_SERVICE_URL` müssen korrekt gesetzt sein.

Start:

```sh
docker compose config
docker compose up -d --build
```

Status und Logs:

```sh
docker compose ps
docker compose logs -f spielplatzkontrolle
```

Der veröffentlichte Host und Port werden mit `PLAYGROUND_BIND_ADDRESS` und `PLAYGROUND_PUBLISHED_PORT` konfiguriert. Standard ist `127.0.0.1:8010` für den Betrieb hinter einem Reverse-Proxy.

Der Healthcheck verwendet automatisch den konfigurierten `PLAYGROUND_BASE_PATH` und prüft den Endpunkt `/api/health`.

Stoppen:

```sh
docker compose down
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Optionale Integrationstests gegen PostgreSQL:

```sh
export PLAYGROUND_TEST_POSTGRES_DSN='postgresql://USER:PASSWORT@HOST:5432/TESTDB'
.venv/bin/python -m unittest tests.test_postgres_integration -v
```

### Django migration acceptance

See [MIGRATION_ACCEPTANCE.md](MIGRATION_ACCEPTANCE.md) for the acceptance
gates and remaining compatibility dependencies. Run `sh tools/verify_migration.sh`
in the project virtual environment before deploying.
