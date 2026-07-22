---
slug: publication_year
title: Veröffentlichungsjahr
kind: metric
produced_by: mod_determine_publication_year
applicability: Vorhanden nach der Analyse; leer, wenn weder Titelseite noch PDF-Metadaten ein plausibles Jahr liefern.
see_also: [module:mod_determine_publication_year, metric:publication_year_source]
---

# Veröffentlichungsjahr (`publication_year`)

Die beste Schätzung des Jahres, in dem die Arbeit eingereicht bzw. veröffentlicht wurde, ermittelt von [mod_determine_publication_year](module:mod_determine_publication_year) durch Fusion des Titelseiten-Jahres mit den PDF-Metadaten.

Dieses Jahr ist die **X-Achse** des Diagramms „Länge über Zeit" im Bericht (SDD §2.1, §9.8) – nicht das rohe `creation_year`, das durch erneutes Speichern häufig verfälscht ist. Welches Signal den Wert gesetzt hat, zeigt [publication_year_source](metric:publication_year_source). Ist kein Jahr ermittelbar, bleibt der Wert leer und die Arbeit erscheint nicht auf der Zeitachse.
