---
slug: fs_modified_year
title: Änderungsjahr der Datei
kind: metric
produced_by: mod_extract_filesystem_metadata
applicability: Immer vorhanden, sobald die Arbeit analysiert wurde und die Datei noch am gespeicherten Ort liegt.
see_also: [module:mod_extract_filesystem_metadata, metric:publication_year, metric:modification_year]
---

# Änderungsjahr der Datei (`fs_modified_year`)

Das Jahr, in dem die PDF-Datei laut Dateisystem zuletzt geändert wurde (mtime), auf **Jahresgenauigkeit** reduziert – kein Tag, keine Uhrzeit. Das Jahr wird in UTC bestimmt, damit dieselbe Datei in einer anderen Zeitzone nicht plötzlich ein anderes Jahr ergibt.

## Wichtig: schwaches Signal

Dieser Wert beschreibt **die Kopie der Datei auf diesem Rechner**, nicht die Arbeit. Kopieren, Herunterladen, Entpacken oder Cloud-Sync setzen den Zeitstempel neu – meist auf den Tag des Kopiervorgangs. In einem frisch heruntergeladenen Korpus steht hier daher oft nur das Jahr des Downloads.

Als Aussage über das Abgabejahr taugt der Wert höchstens als sehr grobe **obere Schranke**: die Arbeit ist nicht *nach* diesem Jahr entstanden.

## Verhältnis zu publication_year

[publication_year](metric:publication_year) fusioniert das Jahr von der Titelseite mit den PDF-Metadaten-Daten. `fs_modified_year` gehört bewusst **nicht** dazu: ein so leicht überschriebener Zeitstempel würde in einer einzigen fusionierten Zahl unsichtbar werden. Wer ihn als letzten Notnagel verwenden möchte, sieht ihn hier als eigene, klar benannte Spalte.
