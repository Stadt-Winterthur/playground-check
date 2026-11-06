# Spielplatzkontrolle

Webanwendung zur Kontrolle von Spielplätzen und zur Bearbeitung von Inspektionen und Mängeln. Frontend und Backend sind in einem Python-Projekt zusammengefasst.

## Technologie

Python 3.11+, Django, Django REST Framework, PostgreSQL/PostGIS sowie HTML, CSS und JavaScript. Die Anwendung wird über Gunicorn als WSGI-Dienst betrieben.

## Lokale Entwicklung

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[django,production]'
cp .env.example .env
# .env mit geeigneten lokalen Entwicklungswerten ausfüllen
./start.sh
```

Keine Zugangsdaten, produktiven Datenbankverbindungen oder Schlüssel ins Repository übernehmen. Für Tests und optionale Qualitätswerkzeuge siehe `requirements/`, `tests/` und `pyproject.toml`.

## Hinweis

Diese Software wurde mit KI-Unterstützung entwickelt.
