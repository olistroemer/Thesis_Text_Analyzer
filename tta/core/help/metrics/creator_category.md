---
slug: creator_category
title: Ausgangsprogramm
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Immer vorhanden, sobald die PDF-Metadaten gelesen wurden; `unknown`, wenn die Datei keine Angabe enthält.
see_also: [module:mod_extract_pdf_metadata, metric:producer_category]
---

# Ausgangsprogramm (`creator_category`)

Die Kategorie des Programms, in dem das Dokument **verfasst** wurde – im Unterschied zu [producer_category](metric:producer_category), das das Programm benennt, welches die PDF-Datei am Ende geschrieben hat. Wertebereich und Vergröberung sind dieselben.

## Wie man den Wert liest

Die Unterscheidung ist im Alltag oft belanglos und manchmal aufschlussreich:

- Bei einer LaTeX-Arbeit stehen häufig beide auf `latex`, oder der Ausgangswert bleibt leer.
- Bei einer Word-Arbeit steht der Ausgangswert auf `word`, während das erzeugende Programm ein PDF-Drucker oder `ghostscript` sein kann.
- Steht hier `word` und dort `ghostscript`, ist die Datei nach dem Schreiben noch durch eine Weiterverarbeitung gelaufen – oft die eines Hochschulrepositoriums. Dabei können Metadaten und Datumsangaben überschrieben worden sein, was [creation_year](metric:creation_year) unbrauchbar macht.

Als Kontrollgröße ist [producer_category](metric:producer_category) die belastbarere der beiden, weil die dort beschriebenen Verzerrungen am letzten Schritt der Kette entstehen. Dieser Wert fehlt häufiger und ist damit als Gruppierungsmerkmal schwächer.

**Nicht zu schließen:** dass die Wahl des Schreibprogramms etwas über die Arbeit aussagt. Sie sagt etwas über Fach, Lehrstuhl und Vorlage – was genau der Grund ist, warum sie als Kontrollgröße nützlich und als Befund uninteressant ist.
