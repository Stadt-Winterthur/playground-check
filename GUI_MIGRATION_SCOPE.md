# GUI-Migration: Status und Freigabegrenzen

Diese Erweiterung ergänzt die serverseitige GUI um Profil und die durch die vorhandenen
nativen Fachbefehle autorisierte Zuweisungsannahme/-ablehnung. Es ist **keine** vollständige
funktionsgleiche Ablösung der Alt-GUI. Nicht vollständig portiert: Inspektionskriterien,
Mängelerfassung/-bearbeitung, Datei- und Bildverwaltung, Administration,
Offline-Synchronisierung, Web-Push. HTMX ist noch nicht als lokal gebundelte Bibliothek
aktiviert. Die alte SPA bleibt aktiv.

Die neuen GET- und POST-Routen sind serverseitig loginpflichtig. POST verlangt CSRF.
Fehlende oder ungültige TIDs werden vor Datenbankzugriff abgewiesen.
Die bestehende SQL-Autorisierung des Zuweisungsbefehls bleibt massgebend.
Vor einer Betriebsfreigabe sind browserbasierte Tests samt Datenbank- und Rollenprüfung nötig.
