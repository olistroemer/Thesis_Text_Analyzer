---
slug: page_count_meta
title: Seiten (PDF-Metadaten)
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Immer vorhanden, sobald die PDF-Metadaten gelesen wurden.
see_also: [module:mod_extract_pdf_metadata, metric:n_pages, metric:extraction_quality]
---

# Seiten (PDF-Metadaten) (`page_count_meta`)

Die Seitenzahl, wie sie sich aus der **Struktur** der PDF-Datei ergibt, gelesen von [mod_extract_pdf_metadata](module:mod_extract_pdf_metadata) mit einer anderen Bibliothek als [n_pages](metric:n_pages).

## Warum es zwei Seitenzahlen gibt

Das ist Absicht und keine Doppelung: Es sind **zwei unabhängige Beobachtungen derselben Größe** mit zwei verschiedenen Bibliotheken.

- Stimmen sie überein – der Normalfall –, ist das ein Hinweis, dass die Datei technisch in Ordnung ist.
- **Weichen sie ab, ist die Datei auffällig.** Möglich sind eine beschädigte Seitenstruktur, eine ungewöhnliche Verschachtelung oder Verschlüsselung, oder eine der beiden Bibliotheken hat abgebrochen. In diesem Fall sind auch alle textbasierten Metriken dieser Zeile mit Vorsicht zu lesen.

Diese Metrik ist damit vor allem ein **Prüfwert**. Für Aussagen über den Umfang einer Arbeit ist [n_pages](metric:n_pages) die Zahl, auf die sich der Rest der Auswertung bezieht.
