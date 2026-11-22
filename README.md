# Unterrichtsmaterial

Materialsammlung als Web-App (GitHub Pages). Schülerinnen, Schüler und Lehrkräfte öffnen sie mit einem Zugangscode – ohne Konto. Bearbeitet wird direkt vom iPad oder Handy.

## Einrichten (einmalig, am Computer)

1. **Neues Repository** auf github.com anlegen, z. B. `unterricht`, **Public**.
   Wichtig: ein *neues* Repository verwenden. Alte, unverschlüsselte Dateien bleiben sonst im Verlauf sichtbar.
2. **Inhalt dieses Ordners hochladen** (*Add file → Upload files*, den Inhalt hineinziehen, nicht den Ordner selbst) → *Commit changes*.
3. **Pages einschalten:** *Settings → Pages → Deploy from a branch → main / (root) → Save*.
   Nach 1–2 Minuten: `https://BENUTZERNAME.github.io/unterricht/`
4. **Token erstellen:** Profilbild → *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*
   - *Only select repositories* → `unterricht`
   - *Repository permissions → Contents: Read and write*
   - Ablaufdatum setzen (z. B. 1 Jahr)
5. Seite öffnen → **Einstellungen** → Benutzername, Repository, Token → *Speichern und testen* → **Ersteinrichtung**:
   Zugangscode (z. B. 4 Ziffern), Prüfungspasswort (mind. 8 Zeichen), Schulform, Jahrgänge.
6. Über **+ Material** die ersten Dateien hochladen.

## Bedienung

- **Bearbeiten** → pro Unterrichtsvorhaben zwei Knöpfe:
  - **+ Unterrichtsmaterial** (für SuS): PDF, interaktive Seite (HTML), Link, Video-Link. Mit dem **Auge** daneben ein- und ausblenden.
  - **+ Lehrkraft-Material**: Word-/PowerPoint-Dateien, Lösungen, Klassenarbeiten. Für SuS **nie** sichtbar.
  - Art und Titel werden aus dem Dateinamen vorgeschlagen („Lösung“ → Lösung, „Klausur/Test/KA“ → Prüfung, `.html` → interaktive Seite).
  - *Klassenarbeit / Test / Klausur* landet immer im Lehrkraft-Bereich und wird zusätzlich mit dem Prüfungspasswort verschlüsselt.
- **+ Material** (oben): wie oben, mit Auswahl von Fach, Jahrgang, Reihe und Vorhaben – auch neue anlegen.
- **Bearbeiten**: außerdem Reihen und Vorhaben anlegen, umbenennen, sortieren, löschen; Titelbild hinterlegen; Reihen aus dem Kernlehrplan ergänzen. Reihen-Karten lassen sich auch im Bearbeiten-Modus öffnen.
- **Fach hinzufügen/bearbeiten → Lehrplan-Vorlage und Symbol**: Mathematik, Physik, Naturwissenschaften (NW 5/6, KLP Gesamtschule) oder Klassenleitung/Sonstiges (Ordner-Vorschläge wie Klassenrat, Elternabend); „automatisch“ erkennt das Fach am Namen.
- **Datei ersetzen**: neue Datei mit **gleichem Dateinamen** hochladen (einzeln oder mehrere) – das vorhandene Material bekommt die neue Datei, Titel, Sichtbarkeit und Kurse bleiben. Einzeln mit Haken „… ersetzen“ (abwählbar).
- **Speichern** läuft im Hintergrund: Änderungen erscheinen sofort, unten links steht „Speichert …“. Nicht mehr gebrauchte Dateien werden danach gelöscht. SuS sehen den neuen Stand nach ca. 1–2 Minuten; Geräte mit Token laden immer den aktuellen Stand direkt von GitHub.
- **Herunterladen**: Jahrgang oder alles als ZIP mit `Übersicht.html` – zum Weiterverwenden ohne diese Seite.
- **Einstellungen** (Zahnrad unten rechts), vier Bereiche: **Info** (kurze Erklärungen zu allen Funktionen), **Zugang** (abmelden, Code/Passwort ändern, GitHub-Token), **Verwaltung** (herunterladen, hochladen, importieren, Vorlagen, Schulform), **Speicher**.

## Mit dem Kurs teilen

- In einer Reihe auf **Mit Kurs teilen** tippen: Link und QR-Code.
- Über den Link sehen SuS nur diese Reihe – ohne Hauptmenü, ohne Ausgeblendetes, ohne Lehrkraft-Material. Das Gerät merkt sich die Reihe.
- Ganz unten: **Alle Materialien herunterladen** – ein ZIP mit allem, was SuS sehen (z. B. zur Vorbereitung auf einen Test).
- **Zurück zur ganzen Sammlung (Lehrkraft):**
  - Auf Geräten mit eingetragenem Token gibt es oben den Knopf **Lehrkraft-Ansicht**; diese Geräte bleiben nie im Kursmodus hängen.
  - Auf anderen Geräten: **5× schnell auf das Fach-Schild** (z. B. „Physik 8“) tippen oder die Adresse mit `#/einstellungen` aufrufen → Reiter **Zugang** → **Kursansicht auf diesem Gerät beenden**.

## Titelbild einer Reihe

- Ein Bild pro Reihe, z. B. Foto oder Export der Concept-Map oder Fragensammlung (außerhalb der App erstellt).
- **Bearbeiten → Titelbild hinzufügen/ändern**. Große Bilder werden beim Hochladen verkleinert.
- Wird oben in der Reihe ganz angezeigt (nicht abgeschnitten); antippen öffnet es groß.
- **Interaktive Seite zum Titelbild** (optional, z. B. Advance Organizer als HTML): im Titelbild-Dialog unter „Beim Antippen öffnen“ eine HTML-Datei oder einen Link wählen. Dann zeigt das Bild links unten „Interaktiv öffnen“, rechts unten bleibt „Vergrößern“. Tipp: Screenshot des Advance Organizers als Titelbild. Ohne Bild erscheint nur der Knopf.
- Links `um:material:Titel` in dieser Seite öffnen Material der Reihe (z. B. Knoten im Advance Organizer → Arbeitsblatt). Die Seite steht nicht in der Materialliste und hat kein „Weiter“.

## Interaktive HTML-Seiten

- HTML-Dateien öffnen sich in der App. Oben gibt es **Zurück** und, wenn es in der Reihe weitergeht, **Weiter**.
- Damit eine Seite selbst zur Oberfläche zurückführt, reichen normale Links:
  - `<a href="#zurueck">Zurück zur Übersicht</a>` – schließt die Seite und zeigt wieder die Reihe
  - `<a href="#weiter">Weiter</a>` – öffnet das nächste Material der Reihe
  - `<a href="um:material:Nachricht an Lena">AB öffnen</a>` – öffnet ein Material der Reihe mit genau diesem Titel
  - in JavaScript: `Plattform.zurueck()`, `Plattform.weiter()`, `Plattform.oeffne('Titel')`
- Speichert die Seite etwas mit `localStorage` (z. B. Fortschritt oder Antworten), bleibt das auf dem Gerät erhalten – getrennt für jede Seite.
- Externe Links öffnen sich in einem neuen Tab.
- Sicherheit: Die Seiten laufen abgeschottet. Sie kommen nicht an Zugangscode, Token oder andere Daten der App.

- **Vorlagen:** Einstellungen → Verwaltung → *Lernpfad* oder *Simulation*. Eine HTML-Datei im Stil der App mit Schritten, Lernziel, Aufgaben, gestuften Hilfen, Quiz, Antwortfeld (wird gespeichert, mit Kopieren-Knopf), Merke-Kasten und Zurück/Weiter. Stellen zum Anpassen sind mit „ÄNDERN“ markiert.

## Ausblenden und Freischalten

- **Stunden:** Bearbeiten → Augen-Symbol rechts in der Zeile.
- **Einzelne Materialien:** Bearbeiten → Augen-Symbol neben dem Material.
- **Ab Datum freischalten:** Im Dialog eines Unterrichtsvorhabens oder Materials „Für SuS sichtbar ab“ setzen. Bis dahin sehen SuS es nicht, danach automatisch – so lässt sich eine Reihe vorausplanen (z. B. Lösungen erst nach der Stunde). Das Auge gilt zusätzlich.
- In der Kursansicht ist Ausgeblendetes unsichtbar, in der Lehrkraft-Ansicht abgedimmt (mit „für SuS ab …“).
- Das Datum kommt vom Gerät der SuS. Es ist eine Planungshilfe, kein Schutz.

## Hinweis für SuS

- Bearbeiten → **Hinweis für SuS anzeigen** (oben in der Reihe), z. B. „Test am Freitag“.
- Optional „Anzeigen bis“: Danach verschwindet der Hinweis von selbst.

## Parallelkurse (z. B. 8a und 8b)

- Bearbeiten → in der Reihe **Parallelkurs anlegen**, Namen eingeben (z. B. „8a“). Weitere Kurse über **+ Kurs** in der Leiste „Freischalten für“.
- Leiste „Freischalten für“: **Standard** oder einen Kurs wählen. Augen, „sichtbar ab“-Termine und der Kurs-Hinweis gelten dann nur für diesen Kurs. Material, Notizen und Checkliste bleiben gemeinsam.
- **Mit 8a teilen:** Jeder Kurs hat einen eigenen Link und QR-Code (`…#/kurs/FACH/JG/REIHE/8a`). Der allgemeine Link zeigt den Standard.
- Neue Vorhaben und Materialien übernehmen den Standard, bis man sie im Kurs anders einstellt.
- Der Hinweis der Reihe gilt für alle Kurse; „Hinweis nur für 8a“ erscheint zusätzlich nur bei 8a.
- Kurs umbenennen behält den Link. Kurs löschen entfernt nur seine Freischaltungen.

## Neues Schuljahr

- Bearbeiten → in der Reihe **Neues Schuljahr**.
  - **Diese Reihe zurücksetzen** oder **Kopie anlegen in …** (beliebiges Fach/Jahrgang).
  - Voreingestellt: alle Vorhaben ausblenden, Lösungen wieder ausblenden, Termine löschen, Hinweise löschen, Parallelkurse entfernen. Optional jedes Material einzeln ausblenden.
  - Material, Notizen (inkl. Reflexion), Checkliste, Titelbild und Reihenfolge bleiben.
- Für alle Reihen eines Jahrgangs auf einmal: auf der Jahrgangsseite **Neues Schuljahr**.
- Eine Kopie nutzt dieselben Dateien (nichts wird neu hochgeladen). Gemeinsam genutzte Dateien werden beim Löschen nicht aus dem Speicher entfernt.

## Checkliste „Ich kann …“

- Bearbeiten → **Checkliste „Ich kann …“ hinterlegen**. Eine Aussage pro Zeile, `#` am Zeilenanfang = Zwischenüberschrift. Oder **aus Datei übernehmen** (Word oder Text, ein Absatz pro Aussage).
- Erscheint nur in Reihen, in denen eine Checkliste hinterlegt ist.
- SuS tippen an: einmal = noch unsicher, zweimal = kann ich sicher. Die Einschätzung bleibt nur auf ihrem Gerät.

## Notizen pro Vorhaben

- Bearbeiten → im Lehrkraft-Bereich eines Vorhabens **Notizen**: Schwerpunktziel, Verlaufsplan, Reflexion („Was lief gut?“). Einfacher Text, kein extra Dokument.
- Nur in der Lehrkraft-Ansicht (aufklappbar wie das Lehrkraft-Material), nie in der Kursansicht oder im SuS-Download. Mit Export und Sicherung gesichert.
- Keine Schülernamen eintragen (Notizen sind mit dem Zugangscode verschlüsselt, siehe unten).

## Niveau ★ / ★★ / ★★★

- Im Material-Dialog **Niveau**: ★ Basis, ★★ Standard, ★★★ Erweiterung (optional).
- Sterne erscheinen am Material – auch für SuS in der Kursansicht.

## Suche

- Lupe oben: durchsucht alle Fächer und Jahrgänge – Reihen, Unterrichtsvorhaben, Materialien, Dateinamen, Hinweise, Checklisten und Notizen. Umlaute können weggelassen werden („bruche“ findet „Brüche“).
- Nicht in der Kursansicht.

## Ordner vom Laptop hochladen (Sammel-Upload)

- **Einstellungen → Verwaltung → Ordner oder Dateien hochladen**, im Bearbeiten-Modus auch in Jahrgang und Reihe. Am Laptop: Ordner wählen oder einfach auf die Seite bzw. auf eine Zeile ziehen. Auf dem iPad: Ordner in der Dateien-App komprimieren und die ZIP wählen, oder mehrere Dateien auf einmal auswählen.
- Erwartete Ablage (wie bisher): `… / 2526 M 6 / M 6 Brüche / M 6 Brüche - 2 Bruchrechnung Fehler.pdf`
  - **Fach und Jahrgang** aus Ordnernamen wie „2526 M 6“, „M 6 Brüche“ oder „Ph Q2“ (M/Ma/Mathe, P/Ph/Physik, NW; 5–10, EF, Q1, Q2). Für NW muss das Fach vorher angelegt sein.
  - **Reihe** = Ordner, in dem die Dateien liegen („M 6 Brüche“ → Reihe „Brüche“).
  - **Unterrichtsvorhaben** = Nummer am Anfang des Dateinamens (einstellbar: Unterordner oder alles in ein Vorhaben).
  - **Kurzer Titel:** „P9 Stromkreis - 3 Blitz-Check - Stationskarten.pdf“ → Vorhaben 3, Titel „Blitz-Check - Stationskarten“. Der Originalname bleibt gespeichert und steht beim Export („Alles herunterladen“) wieder im Dateinamen.
  - **Art** aus Dateiname und Endung („Lösung“, „Klausur/Test/KA“, `.html`, `.pptx` …).
  - **PDF und Word/PowerPoint mit gleichem Namen**: PDF für SuS, Original im Lehrkraft-Bereich. Word/PowerPoint ohne PDF landet im Lehrkraft-Bereich.
  - Ignoriert werden versteckte Dateien und Word-Sperrdateien (`~$…`). Videos werden nicht hochgeladen. `.url`-Verknüpfungen werden zu Links.
- **Vorschau** als Fenster vor der Seite: Ziel (Fach, Jahrgang, Reihe), **Unterrichtsvorhaben pro Datei**, Art, Titel und Bereich prüfen und ändern; Dateien abwählen.

## Einfügen mit Strg+V (Laptop)

- **Dateien aus dem Explorer oder Screenshots** kopieren und in der App einfügen:
  - Maus über einem Unterrichtsvorhaben → die Datei kommt direkt dorthin (über dem Lehrkraft-Bereich: als Lehrkraft-Material). Gibt es die Datei schon, öffnet sich das Fenster zum Zuordnen.
  - Sonst öffnet sich das Fenster zum Zuordnen.
  - In einem offenen Dialog (z. B. Material, Titelbild) füllt Strg+V das Datei-Feld.
- **Text** wird zur Notiz: Vorhaben und Feld (Schwerpunktziel, Verlaufsplan, Reflexion) wählen, Text steht schon drin.
- Screenshots heißen „Screenshot JJJJ-MM-TT hh-mm-ss.png“.
- Material-Dialog: **Enter** speichert, **Entf** löscht (nicht beim Schreiben in einem Feld).

## Im Unterricht

- **Ein- und ausblenden ohne Bearbeiten-Modus:** kleines Auge an jedem Vorhaben und Unterrichtsmaterial (gilt für den gewählten Kurs).
- **„⋯“ an einem Vorhaben:** „Bis hier freischalten“ (alle Vorhaben bis einschließlich diesem) und „Als heute markieren“ (gilt nur heute).
- **Aktuelle Einheit:** Das letzte für SuS sichtbare Vorhaben ist leicht hervorgehoben (solange noch nicht alles freigeschaltet ist). In der Kursansicht springt die Seite dorthin, wenn sie sonst nicht zu sehen wäre. „Heute“ hat Vorrang.
- **QR-Code zu einem Material:** Material öffnen → „QR“. Rechts erscheinen ein QR-Code direkt zu diesem Material (Kursansicht des gewählten Kurses) und ein großes Feld für den Arbeitsauftrag. Der Arbeitsauftrag wird nicht gespeichert. Ist das Material für SuS noch ausgeblendet, gibt es „Jetzt freischalten“. SuS können danach zur Gesamtansicht zurück.
- **Präsentieren:** „Vollbild“ (Taste F), Pfeiltasten → nächstes/vorheriges Material.
- **Tafelbild:** Art „Tafelbild (Foto)“ – am iPad öffnet sich direkt die Kamera, Titel „Tafelbild TT.MM.“.

## Schneller vorbereiten

- **Material kopieren:** Material bearbeiten → Ort (Fach/Jahrgang/Reihe/Vorhaben) wählen → „Als Kopie dort anlegen“. Die Datei wird nicht doppelt gespeichert.
- **Mehrere Materialien:** Bearbeiten → „Auswählen“ (am Laptop: Strg + Klick) → zusammen ein-/ausblenden, verschieben oder löschen (Papierkorb, mit „Rückgängig“).
- **Tastenkürzel (Laptop):** E = Bearbeiten an/aus, / = Suche, N = neues Material im Vorhaben unter der Maus, Esc = Auswahl beenden.

## Papierkorb

- Gelöschtes Material kommt in den Papierkorb (**Einstellungen → Speicher**). Direkt nach dem Löschen: „Rückgängig“ im Hinweis unten.
- Wiederherstellen setzt es an die alte Stelle. Gibt es das Vorhaben nicht mehr, wird es neu angelegt (für SuS ausgeblendet).
- Nach 30 Tagen wird es endgültig gelöscht (beim nächsten Öffnen durch die Lehrkraft), oder vorher über „Papierkorb leeren“.
- Ein gelöschtes Vorhaben legt sein Material ebenfalls in den Papierkorb. Reihen, Jahrgänge und Fächer werden weiter direkt gelöscht (mit Rückfrage).
- **Erneut ausführen = Abgleich**: Unveränderte Dateien werden übersprungen, geänderte ersetzt (erkannt am Ordner oder am gleichen Dateinamen; Titel und Einstellungen bleiben). Auf dem Laptop gelöschte Dateien bleiben in der Sammlung.
- Das passt zur Arbeitsweise: Am Laptop liegt die vollständige Sicherung aller Jahre, in der Sammlung nur, was für den aktuellen Durchgang gebraucht wird.

## Planung importieren und Sicherung wiederherstellen

- **Einstellungen → Verwaltung → Importieren / Wiederherstellen**: ZIP mit `import.json` und Dateien (oder auf dem iPad: `import.json` und Dateien gemeinsam auswählen).
  - **Ergänzen**: Vorhandene Reihen und Vorhaben mit gleichem Namen werden ergänzt, nichts wird überschrieben.
  - **Alles ersetzen**: stellt eine Sicherung („Alles herunterladen“) vollständig wieder her – Fächer mit Farben, Reihenfolge, Ausgeblendetes, Titelbilder, Datei zur Reihe, Lehrkraft-Dateien, Kurs-Links. Prüfungen nur mit Prüfungspasswort (beim Sichern und beim Wiederherstellen).
- Tipp: Ab und zu **Einstellungen → Verwaltung → Alles herunterladen** mit eingegebenem Prüfungspasswort und die ZIP am Laptop ablegen.

## Mehrere Geräte

- Zum Ansehen: auf jedem Gerät einmal den Zugangscode eingeben.
- Zum Bearbeiten: auf jedem Gerät einmal in den Einstellungen GitHub-Name, Repository und Token eintragen.

## Als App installieren

- **iPad/iPhone (Safari):** Teilen → *Zum Home-Bildschirm*
- **Android (Chrome):** Menü → *App installieren*

## Was geschützt ist – und was nicht

- Alle Dateien und die Übersicht liegen **verschlüsselt** (AES-256) im Repository. Ohne Code sieht man nur Datensalat.
- Der Zugangscode ist eine **Zugangshürde** für einen abgegrenzten Personenkreis, kein Tresor: Ein vierstelliger Code lässt sich von technisch Versierten durchprobieren.
- Klassenarbeiten deshalb mit einem **langen** Prüfungspasswort schützen.
- Ein geänderter Code gilt für neue Anmeldungen. Alte Versionen der Zugangsdatei bleiben im Git-Verlauf.
- Keine Namen, Fotos oder Noten von SuS hochladen.
- Notizen und Titel des Lehrkraft-Materials stehen in der Übersicht, die mit dem Zugangscode verschlüsselt ist. Wer den Code kennt und technisch versiert ist, könnte sie lesen – daher nichts Vertrauliches hineinschreiben.

## Dateigrößen

- Möglichst **unter 15 MB** pro Datei (Warnung), höchstens 50 MB. Bei großen PowerPoints für SuS lieber ein PDF hochladen.
- Videos werden nicht hochgeladen, sondern verlinkt. Bilder werden automatisch verkleinert.
- **Einstellungen → Speicher** zeigt den belegten Platz gesamt und pro Fach/Jahrgang, dazu die Größe des Repositorys inkl. Verlauf. Warnung ab ca. 800 MB.
- GitHub Pages: Seite bis 1 GB, ca. 100 GB Datenverkehr pro Monat. Ersetzte Dateien bleiben im Verlauf und zählen mit.
- **Wird es eng:** ein Fach in ein eigenes Repository (eigene Sammlung) auslagern und hier unter *Fach bearbeiten → Adresse* verlinken. Die Startseite zeigt dann einen Knopf zur anderen Sammlung.

## Technik

```
index.html             App
data/zugang.json       Verschlüsselte Schlüssel (wird bei der Einrichtung erstellt)
data/inhalt.enc        Verschlüsselte Übersicht aller Einträge
material/…/*.enc       Verschlüsselte Dateien
lib/pdfjs/             PDF-Anzeige (pdf.js, Apache-2.0)
sw.js, manifest.webmanifest, icons/   App-Funktionen
```
