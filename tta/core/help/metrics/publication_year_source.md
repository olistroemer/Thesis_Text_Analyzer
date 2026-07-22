---
slug: publication_year_source
title: Quelle des Veröffentlichungsjahres
kind: metric
produced_by: mod_determine_publication_year
applicability: Immer vorhanden nach der Analyse; `none`, wenn kein Jahr ermittelt werden konnte.
see_also: [module:mod_determine_publication_year, metric:publication_year]
---

# Quelle des Veröffentlichungsjahres (`publication_year_source`)

Gibt an, welches Signal den Wert von [publication_year](metric:publication_year) gesetzt hat:

- `title_page` – Jahr von der Titelseite des Textes (bevorzugt, am zuverlässigsten).
- `pdf_creation` – Erstellungsjahr aus den PDF-Metadaten.
- `pdf_modification` – Änderungsjahr aus den PDF-Metadaten.
- `none` – kein plausibles Jahr gefunden; das Veröffentlichungsjahr bleibt leer.

Diese Angabe macht transparent, wie belastbar das zugeordnete Jahr ist: Ein `title_page`-Jahr ist deutlich vertrauenswürdiger als ein aus den PDF-Metadaten übernommenes.
