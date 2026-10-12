---
slug: bundled_components
title: Was in diesem Programm steckt
kind: concept
see_also: [module:mod_extract_pymupdf, module:mod_tokenize, module:mod_readability, module:mod_classify_language, module:mod_extract_pdf_metadata]
---

# Was in diesem Programm steckt

Dieses Programm ist nicht von Grund auf neu geschrieben. Wie fast jede Software baut es auf der Arbeit anderer auf: auf frei verfügbaren Bausteinen, die andere Menschen entwickelt haben und unter Bedingungen weitergeben, die eine solche Nutzung erlauben. Diese Seite sagt, welche Bausteine das sind, was jeder davon hier leistet und – wo es eine gibt – wo seine bekannte Schwäche beschrieben ist. Eine genaue technische Aufstellung führt das Projekt in seinem Quelltext, in der Datei `docs/dependencies.md`.

## Das Fundament

**Python** ist die Programmiersprache, in der das Werkzeug geschrieben ist. Das Programm bringt seinen eigenen Python-Interpreter mit; auf Ihrem Rechner muss dafür nichts installiert sein. Zu Python gehört auch **SQLite**, die kleine Datenbank, in der Ihr Projektordner die Ergebnisse aller Auswertungen festhält.

**Tcl/Tk** ist das Fensterwerkzeug: Es zeichnet die Fenster, Menüs, Schaltflächen und Dialoge.

**tksheet** ist die Tabelle, in der Sie die Ergebnisse sehen, sortieren und durchsuchen.

**tomli-w** schreibt die Einstellungsdatei `tta.toml` in Ihrem Projektordner, etwa ob die erweiterte Ansicht eingeschaltet ist.

**PyInstaller** packt all das in eine einzige Datei und entpackt es beim Start wieder in einen vorübergehenden Ordner. Deshalb läuft das Programm ohne Installation – und deshalb braucht es beim Start einen kurzen Augenblick, bevor das Fenster erscheint.

## Vom PDF zum Text

**PyMuPDF** liest den Text aus der PDF-Datei. Das ist der Schritt, auf dem alles Weitere aufbaut: Was hier verloren geht oder verstümmelt wird, fehlt jeder späteren Zahl. Wie gut das gelingt und woran man eine misslungene Extraktion erkennt, steht unter [Text aus dem PDF extrahieren](module:mod_extract_pymupdf) und [Extraktionsqualität prüfen](module:mod_check_extraction_quality).

**pypdf** liest die Angaben, die eine PDF-Datei über sich selbst mitführt – mit welchem Programm und wann sie erzeugt wurde, wie viele Seiten sie hat. Außerdem zählt das Werkzeug damit die eingebetteten Bilder. Was diese Angaben taugen, steht unter [PDF-Metadaten lesen](module:mod_extract_pdf_metadata) und [Abbildungen zählen](module:mod_count_images).

## Sprache und Lesbarkeit

**langdetect** entscheidet, ob eine Arbeit deutsch oder englisch ist. Davon hängt ab, welche Regeln die folgenden Schritte anwenden. Seine typische Fehlentscheidung beschreibt [Sprache erkennen](module:mod_classify_language).

**NLTK** zerlegt den Text in Sätze und Wörter. Für die Satzgrenzen nutzt es ein mitgeliefertes, vortrainiertes Modell namens *Punkt*; was dieses Modell nicht kann, steht unter [In Sätze und Wörter zerlegen](module:mod_tokenize).

**textstat** berechnet den Lesbarkeitswert. Dafür muss es Silben zählen: bei englischen Wörtern mit dem mitgelieferten **CMU-Aussprachewörterbuch**, das über NLTK eingebunden ist, bei deutschen und bei im Wörterbuch fehlenden englischen Wörtern mit **Pyphen**, einer Sammlung von Silbentrennmustern. Wie verlässlich diese Zählung ist, beschreibt [Lesbarkeit berechnen](module:mod_readability).

Alle Sprachdaten – Satzmodell, Aussprachewörterbuch, Trennmuster, Sprachprofile – liegen im Programm selbst. Keiner dieser Bausteine lädt während der Arbeit etwas aus dem Internet nach; das Programm baut keine Netzverbindungen auf.

## Warum die Datei so groß ist

Das Programm ist je nach Betriebssystem rund 50 bis 70 MB groß: unter Windows knapp 50 MB, unter macOS gut 50 MB, unter Linux gut 70 MB. Das Werkzeug selbst ist davon nur ein kleiner Teil. Den Rest macht aus, was es mitbringt, damit es ohne Installation läuft: einen vollständigen Python-Interpreter, das Fensterwerkzeug, die PDF-Bibliothek mit ihrem eingebauten PDF-Kern und die Sprachdaten. Dafür muss auf Ihrem Rechner nichts installiert, eingerichtet oder aktualisiert werden.

## Warum eine Datei voller Lizenzen dabei ist

Jeder dieser Bausteine wurde von seinen Urheberinnen und Urhebern unter Bedingungen freigegeben, die die Weitergabe erlauben – aber nur, wenn ihre Namen und die Bedingungen selbst mit weitergegeben werden. Ein Programm, das in einer einzigen Datei ausgeliefert wird, gibt alle diese Bausteine weiter. Das Projekt kommt dieser Pflicht nach: Jedes veröffentlichte Programm enthält die Datei `THIRD_PARTY_LICENSES.txt` mit den vollständigen Lizenztexten aller enthaltenen Bausteine und den Bedingungen, unter denen dieses Programm selbst steht.

Sie können diese Datei jederzeit öffnen: hier unter [Lizenzen Dritter](app:third_party_licenses) oder über das Menü **Hilfe → Lizenzen Dritter**.

Das Programm selbst und einer seiner Bausteine, PyMuPDF, stehen unter Bedingungen, nach denen bei einer Weitergabe auch der Quelltext erreichbar bleiben muss. Deshalb nennt **Hilfe → Über** die Adresse, unter der er liegt.
