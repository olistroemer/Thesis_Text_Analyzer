---
slug: creation_year
title: Erstellt (Jahr)
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Vorhanden, wenn die PDF-Metadaten ein auswertbares Erstellungsdatum enthalten; sonst leer.
see_also: [module:mod_extract_pdf_metadata, metric:publication_year, metric:publication_year_source, metric:modification_year]
---

# Erstellt (Jahr) (`creation_year`)

Das Jahr, das die PDF-Datei als **Erstellungsdatum** führt. Bewusst nur das Jahr: kein Tag, keine Uhrzeit. Ein sekundengenauer Zeitstempel wäre in Verbindung mit Hochschule und Studiengang ein Personenbezug, ein Jahr ist es nicht.

## Wie man den Wert liest

**Nicht als Veröffentlichungsjahr.** „Erstellt" heißt hier: wann diese PDF-Datei geschrieben wurde – nicht, wann die Arbeit eingereicht wurde. Die beiden fallen regelmäßig auseinander:

- Jedes erneute Speichern oder Neuexportieren setzt das Datum neu. Eine 2015 eingereichte, 2021 für ein Repositorium neu erzeugte Datei trägt 2021.
- Die Weiterverarbeitung durch ein Hochschulrepositorium – Zusammenfügen, Wasserzeichen, Neukomprimierung – überschreibt es ebenfalls.
- Manche Programme schreiben gar kein oder ein offensichtlich falsches Datum (etwa 1970).

Genau deshalb ist **nicht** dieser Wert die Zeitachse dieses Projekts, sondern [publication_year](metric:publication_year), das das Jahr von der Titelseite bevorzugt und dieses hier nur als Ersatz verwendet. Ob im Einzelfall dieser Ersatz gegriffen hat, zeigt [publication_year_source](metric:publication_year_source).

**Nützlich bleibt der Wert als Prüfgröße:** Liegt er weit vor [modification_year](metric:modification_year), ist die Datei nachbearbeitet worden. Liegt er weit hinter dem Jahr von der Titelseite, gilt dasselbe. Ein Korpus, dessen Jahre überwiegend von hier stammen, kann eine zeitliche Aussage nicht tragen.
