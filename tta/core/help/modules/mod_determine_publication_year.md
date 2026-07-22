---
slug: mod_determine_publication_year
title: Veröffentlichungsjahr bestimmen
kind: module
consumes: [raw_text, pdf_metadata]
produces_artefacts: []
produces_metrics: [publication_year, publication_year_source]
applicability: Läuft, sobald extrahierter Text (`raw_text`) und PDF-Metadaten (`pdf_metadata`) vorliegen. Ohne jegliches Datumssignal ist der Lauf trotzdem erfolgreich – mit leerem Jahr und Quelle `none`.
see_also: [metric:publication_year, metric:publication_year_source, module:mod_extract_pdf_metadata]
---

# Veröffentlichungsjahr bestimmen

Dieses Modul liefert die beste Schätzung des **Veröffentlichungsjahres** einer Arbeit – die X-Achse des primären Forschungsziels (SDD §2.1: Textlänge über das Veröffentlichungsjahr). Bisher wurde dafür ersatzweise das unzuverlässige `creation_year` aus den PDF-Metadaten verwendet (durch erneutes Speichern oder Repository-Verarbeitung leicht verfälscht).

## Signalfusion (nach Priorität)

1. **Jahr auf der Titelseite** (aus `raw_text`) – am zuverlässigsten, denn hier steht das Einreichungsjahr. Von mehreren plausiblen Jahreszahlen im führenden Textfenster wird die **jüngste** gewählt (ältere sind meist Zitate); Werte oberhalb des Folgejahres werden verworfen.
2. **`creation_year`** aus den PDF-Metadaten.
3. **`modification_year`** aus den PDF-Metadaten.

Das erste verfügbare Signal gewinnt. Welches es war, hält die Metrik [publication_year_source](metric:publication_year_source) fest; Details der Fusion liegen in den lokalen Lauf-Notizen. Dateisystem-Daten (#18) sind ein mögliches künftiges Notfallsignal, hier aber nicht im Umfang.

## Ergebnis

Zwei Metriken: [publication_year](metric:publication_year) (Zahl, ggf. leer) und [publication_year_source](metric:publication_year_source) (Text). Ist gar kein Datum ermittelbar, bleibt das Jahr leer und die Quelle `none`; im Bericht wird die Arbeit dann auf der Zeitachse ausgelassen.
