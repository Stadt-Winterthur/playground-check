# Test-Baseline vor der Django-Migration

Stand: 23.10.2026. Die bestehenden HTTP- und Antwortformate gelten zunächst als
Kompatibilitätsvertrag; Änderungen müssen bewusst entschieden und getestet werden.

## Lokal ausführen

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Optionaler Schema-Integrationstest (nur gegen eigens dafür bereitgestellte Test-DB,
**niemals gegen PROD**):

```bash
PLAYGROUND_TEST_POSTGRES_DSN='...' python -m unittest discover -s tests -v
```

Ohne `PLAYGROUND_TEST_POSTGRES_DSN` wird der Schematest übersprungen.
Die Tests `test_application.py` und `test_defect_transfer_contract.py` verwenden
Mocks/Fakes und schreiben nicht in Datenbanken.

## Fachliche ID-Invariante (Oracle-Master)

- Die Oracle-Datenbank im Intranet ist Master für **FIDs**.
- Die Spielplatzkontrolle-WebApp generiert bei neuen, für den Nachtabgleich
  bestimmten Datensätzen **TIDs (Transfer-IDs)**, keine neuen FIDs.
- `fid_spielgeraet`, `fid_erfassung` usw. sind bestehende **referenzierende**
  FIDs und dürfen in INSERT/UPDATE vorkommen. Entscheidend ist, dass keine
  *neue* Master-FID vergeben wird.
- Für die Mangel-Erstellung prüft ein Regressionstest insbesondere das
  `PUT /Defect/`-Verhalten, SQL-INSERT/RETURNING `tid`, Exklusivsperre und
  bestehende Fehlermeldungen.
- Dies ist keine Aussage, dass der Nachtabgleich bereits automatisiert getestet
  wäre. Dafür werden separate Integrationstests mit Testdaten in PostgreSQL und
  Oracle bzw. ein definierter Abgleich-Simulator benötigt.

## Noch offene Testlücken

1. Read/Write-API-Verträge aller übrigen fachlichen Endpunkte systematisch
   anhand repräsentativer Antworten und Statuscodes erfassen.
2. Inspektions- und Fotoworkflows inklusive Zuordnung von TIDs und
   referenzierten FIDs testen.
3. Rollback, konkurrierende TID-Erzeugung, ID-Kollisionen mit Datensätzen des
   Nachtabgleichs sowie Idempotenz unter echten Datenbanktransaktionen testen.
4. Berechtigungsmatrix je Rolle für alle schreibenden Endpunkte prüfen.
5. End-to-End-Tests des Frontends und Datenbankintegration mit anonymisierten
   Testdaten einrichten.

**Hinweis:** Die vorhandenen Dokument-Endpunkte verwenden FIDs und eine eigene
`MAX(fid)+1`-Logik. Ob diese Tabellen ebenfalls Oracle-Masterdaten mit
nächtlichem Abgleich sind, muss vor einer Anpassung der Implementierung geklärt
werden. Der vorliegende Schritt verändert diese Logik bewusst nicht.
