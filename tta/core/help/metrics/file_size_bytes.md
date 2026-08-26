---
slug: file_size_bytes
title: Dateigröße
kind: metric
produced_by: mod_extract_filesystem_metadata
applicability: Immer vorhanden, sobald die Arbeit analysiert wurde und die Datei noch am gespeicherten Ort liegt.
see_also: [module:mod_extract_filesystem_metadata, metric:n_pages]
---

# Dateigröße (`file_size_bytes`)

Die Größe der PDF-Datei in **Bytes**, gemessen zum Zeitpunkt der Analyse durch [mod_extract_filesystem_metadata](module:mod_extract_filesystem_metadata).

## Verwendung

Die Dateigröße ist ein grober Umfangsindikator, der stark von der Bebilderung abhängt: eine kurze, scan-lastige Arbeit kann deutlich größer sein als eine lange, rein textliche. Für Umfangsvergleiche sind [word_count](metric:word_count) und [n_pages](metric:n_pages) belastbarer.

Der Wert wird bewusst **doppelt** erhoben: die Spalte `theses.pdf_size_bytes` hält die Größe beim Hinzufügen fest, diese Metrik die Größe beim Analysieren. Weichen beide voneinander ab, wurde die Datei zwischen Hinzufügen und Analyse ausgetauscht oder verändert.
