---
slug: producer_category
title: Erzeugendes Programm
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Immer vorhanden, sobald die PDF-Metadaten gelesen wurden; `unknown`, wenn die Datei keine Angabe enthält.
see_also: [module:mod_extract_pdf_metadata, metric:creator_category, metric:extraction_quality, concept:outlier_detection]
---

# Erzeugendes Programm (`producer_category`)

Die Kategorie des Programms, das die PDF-Datei **geschrieben** hat, gelesen aus den Metadaten der Datei. Mögliche Werte: `latex`, `word`, `libreoffice`, `openoffice`, `indesign`, `ghostscript`, `other` (eine Angabe war vorhanden, passte aber in keine Kategorie) und `unknown` (keine Angabe).

Die Rohzeichenkette – etwa „pdfTeX-1.40.25" – erreicht die Datenbank **nie**; nur die Kategorie wird gespeichert. Sie bleibt im lokalen Zwischenergebnis nachschlagbar und verlässt das Gerät nicht.

## Warum diese Metrik wichtiger ist, als sie aussieht

Sie ist die zentrale **Kontrollgröße** dieses Werkzeugs. Mehrere Verzerrungen der Textauswertung hängen nicht an der Arbeit, sondern am Programm, das die Datei geschrieben hat:

- **Silbentrennung am Zeilenende.** Ein Blocksatz-Dokument aus LaTeX trennt sehr viel häufiger als ein Word-Dokument. Getrennte Wörter überleben die Extraktion als zwei Bruchstücke und verunreinigen alle Wortschatzmetriken – [ttr](metric:ttr), [root_ttr](metric:root_ttr), die Einmalwort-Anteile und [yules_k](metric:yules_k) – sowie [avg_word_len](metric:avg_word_len).
- **Defekte Glyphenzuordnung.** Ältere LaTeX-Ausgaben führen häufiger zu unbrauchbarem Text, siehe [extraction_quality](metric:extraction_quality).
- **Vektor- statt Rastergrafik.** LaTeX-Diagramme werden von [n_images](metric:n_images) nicht gezählt.

## Wie man den Wert benutzt

**Als Prüfschritt, nicht als Ergebnis.** Weil sich die Programmlandschaft über die Jahre wandelt – der Anteil von Word- gegenüber LaTeX-Arbeiten ist 2010 ein anderer als 2025 –, kann jede der obigen Verzerrungen einen **scheinbaren zeitlichen Trend** erzeugen, dem keine Veränderung des Schreibens entspricht.

Daher: Jede Auffälligkeit über die Jahre und jeden Zusammenhang zwischen zwei Metriken zuerst **innerhalb** der Gruppen dieser Metrik nachrechnen. Bleibt der Befund in jeder Gruppe erhalten, ist er belastbarer; verschwindet er, war er ein Werkzeugwandel.

`unknown` und `other` sind keine Restkategorien ohne Bedeutung: Ein Repositorium, das alle Dateien durch dieselbe Weiterverarbeitung schickt, hinterlässt dort einen gemeinsamen Wert und macht damit die Herkunft einer ganzen Teilmenge sichtbar.
