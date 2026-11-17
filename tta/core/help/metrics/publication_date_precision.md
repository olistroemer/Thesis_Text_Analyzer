---
slug: publication_date_precision
title: Genauigkeit des Veröffentlichungsdatums
kind: metric
produced_by: mod_determine_publication_year
applicability: Vorhanden nach der Analyse; leer, wenn kein Jahr ermittelt werden konnte.
see_also: [module:mod_determine_publication_year, metric:publication_year, metric:publication_year_source]
---

# Genauigkeit des Veröffentlichungsdatums (`publication_date_precision`)

Gibt an, wie genau die Angabe war, aus der [publication_year](metric:publication_year) stammt:

- `day` – ein vollständiges Datum („12. Mai 2014").
- `month` – Monat und Jahr („Mai 2014").
- `semester` – ein Semester oder Studienabschnitt („Sommersemester 2014", „WS 2004/05").
- `year` – nur ein Jahr („Berlin, 2009"); ebenso, wenn das Jahr aus den PDF-Metadaten stammt (siehe [publication_year_source](metric:publication_year_source)).
- `year_range` – ein Studienjahr („2020/2021"); gezählt wird das Endjahr.
- leer – kein Jahr ermittelbar.

Die Genauigkeit wird **gespeichert statt aufgefüllt**: Ein Jahr, das nur als „2009" auf der Titelseite steht, wird nicht zu einem erfundenen Datum ergänzt. Das Forschungsziel arbeitet mit dem Jahr; diese Angabe zeigt, wie belastbar die zeitliche Zuordnung ist. Tag und Monat selbst werden nicht gespeichert und nicht exportiert.
