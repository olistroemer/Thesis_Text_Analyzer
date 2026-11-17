---
slug: thesis_type
title: Abschlussart
kind: metric
produced_by: mod_classify_thesis_type
applicability: Immer vorhanden, sobald die Arbeit analysiert wurde; `unspecified`, wenn die ersten Seiten keine eindeutige Angabe enthalten.
see_also: [module:mod_classify_thesis_type]
---

# Abschlussart (`thesis_type`)

Die von [mod_classify_thesis_type](module:mod_classify_thesis_type) aus den ersten Seiten erkannte Abschlussart. Mögliche Werte:

- `bachelor` – eine Bachelorarbeit.
- `master` – eine Masterarbeit.
- `diploma` – eine Diplomarbeit (Abschlüsse vor der Bologna-Umstellung).
- `magister` – eine Magisterarbeit.
- `mas` – eine Abschlussarbeit eines Weiterbildungsmasters (Master of Advanced Studies, Nachdiplomstudium).
- `licentiate` – eine Lizentiatsarbeit.
- `semester` – eine Semester- oder Studienarbeit.
- `doctoral` – eine Dissertation. Die Referenzsammlung enthält keine Dissertation; die Art wird trotzdem erkannt, weil Professorinnen und Professoren auch Promotionen betreuen.
- `unspecified` – keine eindeutige Angabe gefunden (oder Text unbrauchbar).

## Verwendung

Diese Metrik gruppiert die Auswertungen im Bericht: Längenverteilung nach Art, Bachelor-gegen-Master-Vergleich (US-PROF-COMPARE); jede Art bildet eine eigene Gruppe. In der Tabelle erscheint sie in der Spalte „Art".

Vergleichswerte aus einer Referenzsammlung (geplant, #49) gibt es nur für Bachelor- und Masterarbeiten. Die übrigen Arten werden erkannt und angezeigt, gehen aber nicht in solche Vergleichswerte ein: Sie sind dafür zu selten, und die Forschungsfrage betrifft Bachelor- und Masterarbeiten.

`unspecified` ist eine gültige, ehrliche Antwort und kein Fehler. Eine falsch erkannte Art lässt sich – sobald editierbare Metriken (#10) verfügbar sind – manuell korrigieren.
