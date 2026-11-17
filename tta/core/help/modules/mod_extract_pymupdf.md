---
slug: mod_extract_pymupdf
title: Text aus dem PDF extrahieren
kind: module
consumes: []
produces_artefacts: [raw_text, prose_text]
produces_metrics: [text_chars, n_pages, removed_monospace_chars, removed_math_chars]
applicability: Läuft für jede Datei mit der Endung `.pdf`; bei jeder anderen Endung lautet das Ergebnis „nicht anwendbar" („not a PDF").
references: [pymupdf, pdfminer_six]
see_also: [metric:text_chars, metric:n_pages, metric:removed_monospace_chars, metric:removed_math_chars, module:mod_check_extraction_quality, module:mod_tokenize, concept:bundled_components]
---

# Text aus dem PDF extrahieren

Dieses Modul steht am Anfang der Auswertung: Es holt den **Textinhalt** aus der PDF-Datei und legt ihn in zwei Fassungen ab, als `raw_text` und als `prose_text`. Alles, was danach über Sprache, Wortschatz, Satzlängen oder Lesbarkeit gesagt wird, beruht auf diesem Text. Ist er schlecht, sind alle Folgezahlen schlecht – ohne dass man es an ihnen sehen könnte.

## Verfahren

Verwendet wird die Bibliothek PyMuPDF [@pymupdf]. Für jede Seite wird die eingebettete Textebene ausgelesen und die Seiten werden mit einem Seitenumbruchzeichen (Form Feed) aneinandergehängt – dieselbe Konvention wie beim Kommandozeilenwerkzeug `pdftotext`. So bleiben die Seitengrenzen im Text erhalten und ein späterer Vergleich mit anderen Extraktionsbibliotheken bleibt möglich (SDD §2.1.1).

Die Bibliothekswahl ist **bewusst vorläufig** und steht deshalb im Modulnamen. Ein Teil des Projekts besteht darin, mehrere Extraktionsbibliotheken auf denselben Arbeiten zu vergleichen (Kandidaten unter anderem pdfminer.six [@pdfminer_six]); das Modul, das dann gewinnt, ersetzt dieses hier.

## Zwei Fassungen desselben Textes

Jede Seite wird **einmal** ausgelesen; daraus entstehen zwei Fassungen:

- **`raw_text`** ist der vollständige Text der Textebene, genau so, wie das Modul ihn vor dieser Änderung geliefert hat. Ihn lesen die Module, die etwas **erkennen**: [Extraktionsqualität](module:mod_check_extraction_quality), [Sprache](module:mod_classify_language), [Art der Arbeit](module:mod_classify_thesis_type) und [Veröffentlichungsjahr](module:mod_determine_publication_year). Ihre Ergebnisse ändern sich dadurch nicht.
- **`prose_text`** ist derselbe Text **ohne Programmcode und ohne Formeln**. Ihn lesen die Module, die den Text **messen**: [Zerlegung](module:mod_tokenize) und alles, was darauf aufbaut, sowie die [Lesbarkeit](module:mod_readability).

Erkannt werden Code und Formeln an der **Schrift**, nicht am Inhalt: Weggenommen wird jedes Textstück, das in einer Festbreitenschrift gesetzt ist (Code), und jedes, das in einer Formelschrift gesetzt ist (Formeln). Eine Zeile, von der nichts übrig bleibt, verschwindet ganz. Eine Ausnahme schützt Arbeiten, deren **Fließtext** selbst in einer dieser Schriften steht (eine ganz in Courier geschriebene Arbeit, ein Word-Dokument mit Cambria Math als Textschrift): Macht eine der beiden Schriftarten mehr als 80 % des Textes der ganzen Arbeit aus, wird sie für diese Arbeit nicht entfernt. Welche Schriften als Formelschrift gelten und wo das Verfahren danebenliegt, steht bei [removed_math_chars](metric:removed_math_chars) und [removed_monospace_chars](metric:removed_monospace_chars).

Werte der Textmetriken aus früheren Programmversionen, die noch den ungefilterten Text gemessen haben, sind mit den heutigen **nicht vergleichbar**. Die betroffenen Module haben deshalb neue Versionsnummern und werden beim nächsten Lauf neu berechnet. Auf dem Referenzkorpus des Projekts lagen die Änderungen meist bei wenigen Prozent und betrafen vor allem Informatik, Mathematik und Physik.

## Ergebnis

- [text_chars](metric:text_chars) – Anzahl der Zeichen im Text ohne Code und Formeln (`prose_text`).
- [n_pages](metric:n_pages) – Anzahl der Seiten, die eine Textebene geliefert haben.
- [removed_monospace_chars](metric:removed_monospace_chars) und [removed_math_chars](metric:removed_math_chars) – wie viele Zeichen als Code beziehungsweise als Formel entfernt wurden.
- die Zwischenergebnisse `raw_text` und `prose_text` – die beiden Textfassungen, nur lokal gespeichert und nie Teil eines Exports.

## Was Extraktion nicht ist

**Extraktion ist kein Lesen.** Ein PDF beschreibt, welches Glyph an welcher Position gezeichnet wird; welcher Buchstabe das ist, steht in einer Zuordnungstabelle der eingebetteten Schrift. Fehlt oder ist diese Tabelle defekt, entsteht **deterministischer Zeichenmüll**: kein Fehler, keine Warnung, sondern flüssig aussehender Unsinn, aus dem alle Metriken anschließend brav berechnet werden. Genau darauf prüft [mod_check_extraction_quality](module:mod_check_extraction_quality) – der Grund, warum es dieses Modul überhaupt gibt.

**Der Text ist unstrukturiert.** Kopf- und Fußzeilen, Seitenzahlen, Inhaltsverzeichnis, Bildunterschriften, Tabelleninhalte und das gesamte Literaturverzeichnis landen auch im `prose_text` – unmarkiert und mit demselben Gewicht wie der Fließtext; nur Code und Formeln werden herausgenommen. Nachgelagerte Module können den Rest nicht unterscheiden. Eine Arbeit mit 40 Seiten Tabellenanhang misst zu einem Teil ihren Anhang.

**Die Leserichtung ist eine Vermutung.** Bei mehrspaltigen Seiten, Textfeldern und um Abbildungen herum geflossenem Text kann die Reihenfolge der extrahierten Wörter von der gelesenen abweichen. Auf Wort- und Zeichenzählungen wirkt sich das nicht aus, auf Satzgrenzen und Wortfolgen ([mod_redundancy](module:mod_redundancy)) durchaus.

## Lizenzhinweis

PyMuPDF steht unter der AGPL. Das Projekt insgesamt steht unter einer Copyleft-Lizenz (ADR-0017), deshalb darf die Bibliothek mitgeliefert werden. Die frühere Auflage, sie vor der ersten Verteilung zu ersetzen, ist damit hinfällig; verglichen wird jetzt nach Extraktionsqualität, nicht nach Lizenz.
