---
slug: modification_year
title: Geändert (Jahr)
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Vorhanden, wenn die PDF-Metadaten ein auswertbares Änderungsdatum enthalten; sonst leer.
see_also: [module:mod_extract_pdf_metadata, metric:creation_year, metric:fs_modified_year, metric:publication_year]
---

# Geändert (Jahr) (`modification_year`)

Das Jahr, das die PDF-Datei als **Änderungsdatum** führt, auf Jahresgenauigkeit reduziert. Es steht *in* der Datei und ist damit von [fs_modified_year](metric:fs_modified_year) zu unterscheiden, das das Dateisystem dieses Rechners liefert.

## Wie man den Wert liest

Das schwächste der drei Datumssignale und die **letzte** Rückfallebene bei der Bestimmung von [publication_year](metric:publication_year). Er beschreibt, wann die Datei zuletzt angefasst wurde – von wem und warum, steht nirgends. Ein Wasserzeichen eines Repositoriums, eine Neukomprimierung oder ein Öffnen-und-Speichern genügt.

Zwei sinnvolle Verwendungen:

- **Als obere Schranke.** Die Arbeit ist nicht *nach* diesem Jahr entstanden.
- **Im Vergleich mit [creation_year](metric:creation_year).** Sind beide gleich, wurde die Datei nach dem Erzeugen nicht mehr verändert – das Erstellungsjahr ist dann etwas glaubwürdiger. Liegen Jahre dazwischen, ist die Datei nachbearbeitet und beide Datumsangaben sind als Einreichungsjahr unbrauchbar.

Ist dies laut [publication_year_source](metric:publication_year_source) die Quelle des Veröffentlichungsjahres einer Arbeit, sollte diese Arbeit aus zeitlichen Auswertungen eher herausgenommen als mitgeführt werden.
