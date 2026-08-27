---
slug: mod_extract_pdf_metadata
title: PDF-Metadaten lesen
kind: module
consumes: []
produces_artefacts: [pdf_metadata]
produces_metrics: [page_count_meta, producer_category, creator_category, creation_year, modification_year, has_outline]
applicability: Läuft für jede Datei mit der Endung `.pdf`; bei jeder anderen Endung lautet das Ergebnis „nicht anwendbar" („not a PDF").
references: [pypdf]
see_also: [metric:producer_category, metric:creation_year, module:mod_determine_publication_year, module:mod_extract_filesystem_metadata]
---

# PDF-Metadaten lesen

Jede PDF-Datei führt einen Satz technischer Angaben mit sich: mit welchem Programm sie erzeugt wurde, wann, wie viele Seiten sie hat – und oft auch Titel und Verfassername. Dieses Modul liest sie mit `pypdf` [@pypdf] aus.

## Datenschutz ist hier die Hauptentscheidung

Die **vollständigen** Angaben, einschließlich `Author` und `Title`, werden in ein lokales Zwischenergebnis geschrieben. Dieses Zwischenergebnis wird **nie exportiert** und verlässt das Gerät unter keinen Umständen.

Zu Metriken – und damit zu exportierbaren Werten – werden nur **sechs geprüfte Angaben**, und zwei davon in bewusst vergröberter Form:

- Aus den Programmnamen wird eine **Kategorie**. Die Rohzeichenkette („Microsoft® Word für Microsoft 365") erreicht die Datenbank nie, sondern nur `word`. Gesucht wird nach charakteristischen Bestandteilen in fester Reihenfolge; der erste Treffer gewinnt. Bekannte Kategorien sind `latex`, `word`, `libreoffice`, `openoffice`, `indesign` und `ghostscript`; alles andere ist `other`, eine leere Angabe ist `unknown`.
- Aus den Datumsangaben wird nur das **Jahr**. Kein Tag, keine Uhrzeit. Ein Zeitstempel auf die Sekunde in Verbindung mit einer Hochschule und einem Studiengang ist ein Personenbezug; ein Jahr ist es nicht.

Weitere technische Angaben – PDF-Version, Verschlüsselungs- und Formularmerkmale – bleiben im lokalen Zwischenergebnis und werden **nicht** zu Metriken. Sie tragen für die Forschungsfrage wenig bei und wären jederzeit nachträglich zu ergänzen (ADR-0011).

## Ergebnis

| Metrik | Bedeutung |
|---|---|
| [page_count_meta](metric:page_count_meta) | Seitenzahl laut PDF-Struktur |
| [producer_category](metric:producer_category) | Kategorie des erzeugenden Programms |
| [creator_category](metric:creator_category) | Kategorie des Ausgangsprogramms |
| [creation_year](metric:creation_year) | Erstellungsjahr laut Metadaten |
| [modification_year](metric:modification_year) | Änderungsjahr laut Metadaten |
| [has_outline](metric:has_outline) | ob die Datei einen Lesezeichenbaum hat |

## Einschränkungen

**Metadaten sind eine Behauptung, keine Beobachtung.** Sie enthalten, was das erzeugende Programm hineingeschrieben hat. Sie können fehlen, falsch sein oder nachträglich geändert worden sein; jedes erneute Speichern und jede Verarbeitung durch ein Hochschulrepositorium kann sie überschreiben.

**Die Datumsangaben sind keine Veröffentlichungsdaten.** Eine 2015 eingereichte, 2021 neu exportierte Arbeit trägt 2021. Deshalb ist [creation_year](metric:creation_year) **nicht** die Zeitachse dieses Projekts, sondern nur ein Ersatzsignal in [mod_determine_publication_year](module:mod_determine_publication_year) – und welches Signal am Ende gewonnen hat, steht in [publication_year_source](metric:publication_year_source).

**Zwei Programmangaben, zwei Bedeutungen.** `Creator` benennt das Programm, in dem der Text entstand (etwa Word oder ein LaTeX-Editor), `Producer` das Programm, das die PDF-Datei geschrieben hat (etwa pdfTeX oder ein Ghostscript-Durchlauf). Sie stimmen häufig nicht überein, und beide können leer sein.

**`producer_category` ist trotzdem eine der wichtigsten Metriken** – nicht wegen ihrer eigenen Aussage, sondern als **Kontrollgröße**. Mehrere Verzerrungen der Textauswertung hängen am erzeugenden Programm: Silbentrennung am Zeilenende, defekte Glyphenzuordnungen, Vektor- statt Rastergrafiken. Und weil sich die Programmlandschaft über die Jahre wandelt, kann daraus ein scheinbarer zeitlicher Trend entstehen, dem keine Veränderung des Schreibens entspricht. **Jede zeitliche Aussage sollte gegen `producer_category` geprüft werden.**
