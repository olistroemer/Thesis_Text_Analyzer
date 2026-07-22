---
slug: mod_classify_thesis_type
title: Abschlussart erkennen
kind: module
consumes: [raw_text]
produces_artefacts: []
produces_metrics: [thesis_type]
applicability: Läuft, sobald der extrahierte Text (`raw_text`) vorliegt. Bei unlesbarem oder sehr kurzem Text wird `unspecified` zurückgegeben – nie „nicht anwendbar".
see_also: [metric:thesis_type, module:mod_classify_language]
---

# Abschlussart erkennen

Dieses Modul bestimmt die **Abschlussart** einer Arbeit (Bachelor- oder Masterarbeit) allein aus dem Text der **Titelseite**. Es ersetzt den früheren Auswahldialog beim Hinzufügen von Dateien: Die Art wird jetzt automatisch erkannt (siehe [ADR-0019]) und kann später über editierbare Metriken korrigiert werden (#10).

## Verfahren

Untersucht wird das führende Textfenster (etwa die erste Seite). Der Text wird zunächst normalisiert – Klein­schreibung, Auflösung von Umlauten und Akzenten, Vereinheitlichung von Apostrophen –, danach wird nach charakteristischen Schlüsselwörtern gesucht:

- **Deutsch:** „Bachelorarbeit", „Masterarbeit", „Masterthesis", „Bachelorthesis", …
- **Englisch:** „Bachelor's thesis", „Master's thesis", „B.Sc.", „M.Sc.", „Master of Science", …

Das ist eine bewusst **leichtgewichtige Heuristik** (keine KI/kein Modell). Werden Marker beider Arten gefunden, gewinnt der zuerst auf der Seite genannte. Fehlt jeder eindeutige Marker – oder ist der Text unbrauchbar –, lautet das Ergebnis `unspecified`.

## Ergebnis

Erzeugt die einzelne Metrik [thesis_type](metric:thesis_type) mit einem der Werte `bachelor`, `master` oder `unspecified`. Es gibt bewusst **keine** separate Konfidenz-Metrik; die gefundenen Schlüsselwörter werden als Beleg in den lokalen Lauf-Notizen abgelegt (verlassen das Gerät nie).
