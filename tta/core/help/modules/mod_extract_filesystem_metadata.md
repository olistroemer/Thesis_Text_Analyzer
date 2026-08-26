---
slug: mod_extract_filesystem_metadata
title: Dateisystem-Metadaten lesen
kind: module
consumes: []
produces_artefacts: []
produces_metrics: [file_size_bytes, fs_modified_year]
applicability: Läuft, solange die Datei noch unter dem gespeicherten Pfad liegt. Fehlt die Datei, lautet das Ergebnis „nicht anwendbar" („file not found").
see_also: [metric:file_size_bytes, metric:fs_modified_year, module:mod_determine_publication_year]
---

# Dateisystem-Metadaten lesen

Dieses Modul liest **nicht** den Inhalt der PDF-Datei, sondern nur, was das Dateisystem über sie weiß: ihre **Größe** und ihren **Änderungszeitpunkt**. Es benötigt dafür keine Bibliothek – nur `os.stat` aus der Standardbibliothek.

## Ergebnis

- [file_size_bytes](metric:file_size_bytes) – die Dateigröße in Bytes, gemessen **zum Analysezeitpunkt**. Die Spalte `theses.pdf_size_bytes` hält den Wert vom Hinzufügen fest; weichen beide voneinander ab, wurde die Datei zwischenzeitlich ausgetauscht.
- [fs_modified_year](metric:fs_modified_year) – das **Jahr** der letzten Änderung (mtime). Bewusst nur das Jahr, wie schon bei den PDF-Metadaten: kein Tag, keine Uhrzeit.

## Wichtige Einschränkung: schwache Signale

Zeitstempel des Dateisystems beschreiben **die Kopie der Datei auf diesem Rechner**, nicht die Arbeit selbst. Kopieren, Herunterladen, Entpacken oder Cloud-Sync setzen sie neu. `fs_modified_year` ist deshalb höchstens eine sehr grobe **obere Schranke** für das Abgabejahr.

Genau deshalb fließt der Wert **nicht** in die Berechnung von [publication_year](metric:publication_year) ein: eine fusionierte Zahl würde diese Schwäche verdecken. Das Signal bleibt sichtbar und klar benannt für sich stehen.

## Was bewusst nicht erfasst wird

- **atime (letzter Zugriff)** – ist praktisch wertlos: Mount-Optionen wie `noatime`/`relatime` schalten ihn häufig ab, und schon das Lesen der PDF-Datei während der Analyse setzt ihn neu. Die Metrik würde also teilweise das Programm selbst messen.
- **ctime / Erstellungszeit** – bedeutet auf Windows etwas anderes als auf Linux (Erstellungszeit gegenüber Inode-Änderungszeit), und `st_birthtime` gibt es unter Linux nicht. Ein Metrikname würde damit je nach Betriebssystem Unterschiedliches bedeuten.

Beide Werte werden in voller Genauigkeit in den **lokalen Lauf-Notizen** abgelegt: nachschlagbar auf dem Rechner, der sie erzeugt hat, aber nie Teil eines Exports.
