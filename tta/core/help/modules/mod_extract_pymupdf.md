---
slug: mod_extract_pymupdf
title: Text aus dem PDF extrahieren
kind: module
consumes: []
produces_artefacts: [raw_text]
produces_metrics: [text_chars, n_pages]
applicability: Läuft für jede Datei mit der Endung `.pdf`; bei jeder anderen Endung lautet das Ergebnis „nicht anwendbar" („not a PDF").
references: [pymupdf, pdfminer_six]
see_also: [metric:text_chars, metric:n_pages, module:mod_check_extraction_quality, module:mod_tokenize, concept:bundled_components]
---

# Text aus dem PDF extrahieren

Dieses Modul steht am Anfang der Auswertung: Es holt den **Textinhalt** aus der PDF-Datei und legt ihn als Zwischenergebnis `raw_text` ab. Alles, was danach über Sprache, Wortschatz, Satzlängen oder Lesbarkeit gesagt wird, beruht auf diesem einen Text. Ist er schlecht, sind alle Folgezahlen schlecht – ohne dass man es an ihnen sehen könnte.

## Verfahren

Verwendet wird die Bibliothek PyMuPDF [@pymupdf]. Für jede Seite wird die eingebettete Textebene ausgelesen und die Seiten werden mit einem Seitenumbruchzeichen (Form Feed) aneinandergehängt – dieselbe Konvention wie beim Kommandozeilenwerkzeug `pdftotext`. So bleiben die Seitengrenzen im Text erhalten und ein späterer Vergleich mit anderen Extraktionsbibliotheken bleibt möglich (SDD §2.1.1).

Die Bibliothekswahl ist **bewusst vorläufig** und steht deshalb im Modulnamen. Ein Teil des Projekts besteht darin, mehrere Extraktionsbibliotheken auf denselben Arbeiten zu vergleichen (Kandidaten unter anderem pdfminer.six [@pdfminer_six]); das Modul, das dann gewinnt, ersetzt dieses hier.

## Ergebnis

- [text_chars](metric:text_chars) – Anzahl der Zeichen im extrahierten Text.
- [n_pages](metric:n_pages) – Anzahl der Seiten, die eine Textebene geliefert haben.
- das Zwischenergebnis `raw_text` – der vollständige Text, nur lokal gespeichert und nie Teil eines Exports.

## Was Extraktion nicht ist

**Extraktion ist kein Lesen.** Ein PDF beschreibt, welches Glyph an welcher Position gezeichnet wird; welcher Buchstabe das ist, steht in einer Zuordnungstabelle der eingebetteten Schrift. Fehlt oder ist diese Tabelle defekt, entsteht **deterministischer Zeichenmüll**: kein Fehler, keine Warnung, sondern flüssig aussehender Unsinn, aus dem alle Metriken anschließend brav berechnet werden. Genau darauf prüft [mod_check_extraction_quality](module:mod_check_extraction_quality) – der Grund, warum es dieses Modul überhaupt gibt.

**Der Text ist unstrukturiert.** Kopf- und Fußzeilen, Seitenzahlen, Inhaltsverzeichnis, Bildunterschriften, Tabelleninhalte, Formelfragmente und das gesamte Literaturverzeichnis landen im `raw_text` – unmarkiert und mit demselben Gewicht wie der Fließtext. Nachgelagerte Module können sie nicht unterscheiden. Eine Arbeit mit 40 Seiten Tabellenanhang misst zu einem Teil ihren Anhang.

**Die Leserichtung ist eine Vermutung.** Bei mehrspaltigen Seiten, Textfeldern und um Abbildungen herum geflossenem Text kann die Reihenfolge der extrahierten Wörter von der gelesenen abweichen. Auf Wort- und Zeichenzählungen wirkt sich das nicht aus, auf Satzgrenzen und Wortfolgen ([mod_redundancy](module:mod_redundancy)) durchaus.

## Lizenzhinweis

PyMuPDF steht unter der AGPL. Das Projekt insgesamt steht unter einer Copyleft-Lizenz (ADR-0017), deshalb darf die Bibliothek mitgeliefert werden. Die frühere Auflage, sie vor der ersten Verteilung zu ersetzen, ist damit hinfällig; verglichen wird jetzt nach Extraktionsqualität, nicht nach Lizenz.
