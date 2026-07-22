---
slug: thesis_type
title: Abschlussart
kind: metric
produced_by: mod_classify_thesis_type
applicability: Immer vorhanden, sobald die Arbeit analysiert wurde; `unspecified`, wenn die Titelseite keine eindeutige Angabe enthält.
see_also: [module:mod_classify_thesis_type]
---

# Abschlussart (`thesis_type`)

Die von [mod_classify_thesis_type](module:mod_classify_thesis_type) aus der Titelseite erkannte Abschlussart. Mögliche Werte:

- `bachelor` – die Titelseite nennt eine Bachelorarbeit.
- `master` – die Titelseite nennt eine Masterarbeit.
- `unspecified` – keine eindeutige Angabe gefunden (oder Text unbrauchbar).

## Verwendung

Diese Metrik gruppiert die Auswertungen im Bericht: Längenverteilung nach Art, Bachelor-gegen-Master-Vergleich (US-PROF-COMPARE). In der Tabelle erscheint sie in der Spalte „Type".

`unspecified` ist eine gültige, ehrliche Antwort und kein Fehler. Eine falsch erkannte Art lässt sich – sobald editierbare Metriken (#10) verfügbar sind – manuell korrigieren.
