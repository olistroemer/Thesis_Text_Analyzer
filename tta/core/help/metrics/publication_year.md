---
slug: publication_year
title: Veröffentlichungsjahr
kind: metric
produced_by: mod_determine_publication_year
applicability: Vorhanden nach der Analyse; leer, wenn weder Titelseite noch PDF-Metadaten ein plausibles Jahr liefern.
see_also: [module:mod_determine_publication_year, metric:publication_year_source, metric:publication_date_precision]
---

# Veröffentlichungsjahr (`publication_year`)

Die beste Schätzung des Jahres, in dem die Arbeit eingereicht bzw. veröffentlicht wurde, ermittelt von [mod_determine_publication_year](module:mod_determine_publication_year): bevorzugt das Datum, das die Titelseite nennt (nach festen Regeln, die Geburts-, Prüfungs-, Copyright- und ähnliche Daten ausschließen), sonst das Jahr aus den PDF-Metadaten.

Dieses Jahr ist die **X-Achse** der Diagramme „… über die Zeit" im Bericht (SDD §2.1, §9.8) – nicht das rohe `creation_year`, das durch erneutes Speichern häufig verfälscht ist. Welches Signal den Wert gesetzt hat, zeigt [publication_year_source](metric:publication_year_source), wie genau die zugrunde liegende Angabe war, [publication_date_precision](metric:publication_date_precision). Ein Wintersemester zählt mit seinem Endjahr. Ist kein Jahr ermittelbar, bleibt der Wert leer und die Arbeit erscheint nicht auf der Zeitachse.
