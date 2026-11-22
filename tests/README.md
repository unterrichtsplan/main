# Tests

Automatische Prüfung der App im Browser – mit einem **simulierten GitHub** (keine echten Daten, kein Token, Testcode `1234`, Testpasswort `pruefung123`).

## Ausführen

```
pip install playwright
python -m playwright install chromium   # einmalig, falls kein Chrome vorhanden
python tests/run.py                     # prüft die App im übergeordneten Ordner
```

* Optional: `CHROME=/pfad/zu/chrome python tests/run.py`
* Ergebnis: `OK …` / `FAIL …` pro Prüfung, am Ende `n/n bestanden`.
* Screenshots und Testdateien landen in `tests/out/` (nicht im Repository).

## Was geprüft wird

* Ersteinrichtung, Migration alter Daten (Datenmodell v1 → v2)
* Upload SuS-/Lehrkraft-Material, Prüfungen mit Prüfungspasswort, Videos abgelehnt, Titelbild verkleinert
* Kursansicht (nur SuS-Sichtbares, Lehrkraft-Knopf, versteckter Rückweg), SuS-ZIP
* Sammel-Upload mit Ordnerstruktur `2526 M 6 / M 6 Brüche / …`, Abgleich (unverändert/geändert), Drag-and-drop, Mehrfachauswahl
* HTML-Seiten: Abschottung, `#zurueck`/`#weiter`, Sprunglinks, gespeicherter Fortschritt
* Freischalten ab Datum, Hinweis-Banner, Checkliste (auch aus Word), Suche, Vorlagen (Lernpfad + Simulation: schmale Kopfzeile, ein Bildschirm, Schritte)
* Einstellungen in Kategorien (Info, Zugang, Verwaltung, Speicher), keine Erklärtexte in Suche und Reihe
* Notizen pro Vorhaben (nur Lehrkraft), Niveau ★/★★/★★★ (auch Kursansicht)
* Parallelkurse (eigene Freischaltung, Termine, Hinweis, Link), neues Schuljahr (Kopie mit gemeinsamen Dateien, Zurücksetzen)
* Verschieben per Ziehen (Vorhaben, Material im eigenen Bereich, Reihen), Pfeiltasten am Griff, Antippen öffnet weiter
* Buchaufgabe (Titel sichtbar, Hinweis antippbar, Suche, Sicherung), Auswahl „Art“ (Dokument/Lösung/Prüfung/Buch), Material zwischen Bereichen und Vorhaben verschieben (Rückfrage, Prüfung bleibt Lehrkraft), Lehrkraft-Bereich offen, SuS-Ansicht
* Formatierung (**fett**, *kursiv*, Liste, kein eingeschleustes HTML), iPad: Teilen statt Herunterladen (Viewer, ZIP)
* Export → Import („Ergänzen“) und Sicherung → „Alles ersetzen“ (verlustfrei)

## Erweitern

Neue Prüfungen vor dem Abschnitt „C: Sicherung“ in `run.py` einfügen (`check('Name', Bedingung, Info)`).
Echte Unterrichtsmaterialien nicht ins Repository legen – Testdateien im Skript erzeugen.
* Mehrere Tage: Trenner „+ Tag“ im Vorhaben (verschieben, umbenennen, löschen, SuS nur mit Material danach, nicht in Suche, Sicherung)
* Titelbild mit interaktiver Seite (Advance Organizer): nur HTML/Link, Knopf auf dem Bild, Vergrößern bleibt, `um:material:` öffnet Material, Kursansicht, SuS-Download, ohne Bild nur Knopf, Link statt Datei, Sicherung
* Einfügen (Strg+V): Datei über Vorhaben direkt, ohne Ziel Fenster zum Zuordnen (vor der Seite, Vorhaben pro Datei), Screenshot-Name, Datei-Feld im Dialog, Text als Notiz; Kurztitel aus „P9 Stromkreis - 3 …“, Originalname im Export; Enter speichert, Entf löscht; Papierkorb (Rückgängig, Wiederherstellen, Leeren, nach 30 Tagen)
* Unterricht: Auge/„⋯“ ohne Bearbeiten, Bis hier freischalten, aktuelle Einheit + „heute“, Direktlink `?m=` in der Kursansicht, QR + Arbeitsauftrag (nicht gespeichert), Pfeiltasten, Tafelbild, Kopie in andere Reihe, Mehrfachauswahl (Ein/Aus, Papierkorb, Rückgängig, Strg + Klick, Esc), Tastenkürzel E / N
* Planung pro Reihe (Kasten, Kästchen abhaken, Strg+V, Suche, nie in Kursansicht), „+ Material“-Menü, Lehrkraft-Bereich zu/offen, Bearbeiten-Modus: Antippen öffnet Material, Stift öffnet Dialog, Info in Gruppen. Helfer `pen()` (Stift am Material) und `sus_ansicht()` (über „Mit Kurs teilen“).
