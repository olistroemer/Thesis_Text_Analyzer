---
slug: n_images
title: Abbildungen
kind: metric
produced_by: mod_count_images
applicability: Immer vorhanden, sobald die Datei als PDF gelesen werden konnte.
see_also: [module:mod_count_images, metric:producer_category, metric:file_size_bytes]
---

# Abbildungen (`n_images`)

Die Zahl der in der PDF-Datei **eingebetteten Bilddaten**, gezählt von [mod_count_images](module:mod_count_images).

## Wie man den Wert liest

Trotz der Spaltenbeschriftung: Das ist **nicht die Zahl der Abbildungen** der Arbeit. Gezählt werden Bilddateien im PDF, und die stimmen mit den Abbildungen des Dokuments in beiden Richtungen nicht überein:

- **Zu niedrig** bei Vektorgrafiken. Ein mit LaTeX-Werkzeugen gesetztes Diagramm ist eine Folge von Zeichenbefehlen und enthält kein Bild. Eine Arbeit mit 30 solchen Diagrammen steht hier bei 0.
- **Zu hoch** bei gekachelten Rasterbildern (jede Kachel zählt), bei Hochschullogos und Kopfzeilengrafiken (teils auf jeder Seite) und bei gescannten Arbeiten (ein Bild je Seite).

Weil die erste Verzerrung an der Arbeitsweise mit dem Schreibprogramm hängt, korreliert dieser Wert stark mit [producer_category](metric:producer_category) – LaTeX-Arbeiten erscheinen systematisch bildärmer als Word-Arbeiten, auch wenn sie es nicht sind.

**Nicht zu schließen:** dass eine Arbeit mit niedrigem Wert wenig visualisiert. Brauchbar ist der Wert als Rangordnung **innerhalb** einer Gruppe gleicher `producer_category`, und als Hinweis auf einen Scan, wenn er ungefähr [n_pages](metric:n_pages) entspricht und der Text unbrauchbar ist.
