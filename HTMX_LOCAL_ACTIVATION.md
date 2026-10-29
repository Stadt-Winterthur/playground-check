# HTMX lokal aktivieren (Online-Anwendung)

Die bestehende Django-GUI unter `/__ui/` hat bereits `hx-get`-Suchfelder und serverseitige HTML-Fragment-Antworten. Die Layout-Vorlage laedt `static/vendor/htmx.min.js` **nur, wenn diese Datei vorhanden ist**. Die GUI funktioniert auch ohne HTMX ueber normale Formular-Requests.

## Installation im Entwicklungs-Repository

Einmalig in einer Entwicklungsumgebung mit Internetzugriff ausfuehren:

```bash
python tools/fetch_htmx_verified.py
python -m unittest discover -s tests -v
git add tools/fetch_htmx_verified.py tests/test_htmx_vendor_integrity.py HTMX_LOCAL_ACTIVATION.md src/playground_check/static/vendor/htmx.min.js
git commit -m "Vendor verified HTMX 2.0.11 for Django GUI"
git push
```

Das Skript laedt eine feste Version aus der offiziellen npm-Auslieferung, vergleicht den SHA-384-Hash mit dem dokumentierten Upstream-SRI und schreibt die Datei erst **nach erfolgreicher Verifikation** ins Repository. In der produktiven/testseitigen Laufzeit erfolgen **keine externen CDN-Abfragen**. Wenn das Herunterladen fehlschlaegt, wird keine Datei ersetzt.

Nach dem Deployment im Browser (angemeldet) `/stadtgruen/spielplatzkontrolle/__ui/assigned/` und `/stadtgruen/spielplatzkontrolle/__ui/playgrounds/` testen: Suchfeld-Eingaben aktualisieren die Ergebnisliste ohne vollstaendigen Seitenwechsel. Ohne Login muessen diese Routen weiterhin 401 liefern; der serverseitige Zugriffsschutz wird durch HTMX nicht ersetzt.

**Kein Offline-Modus.** Keine Entwurfsablage, kein IndexedDB, keine automatische Synchronisierung. Die Inspektionsschreibfreigabe wird durch diesen Schritt nicht geaendert.
