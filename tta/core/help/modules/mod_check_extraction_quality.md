---
slug: mod_check_extraction_quality
title: Extraktionsqualität prüfen
kind: module
consumes: [raw_text]
produces_artefacts: []
produces_metrics: [extraction_quality]
applicability: Läuft, sobald der extrahierte Text (`raw_text`) vorliegt. Ist die Extraktion selbst gescheitert, entfällt der Lauf mit der Begründung des vorgelagerten Moduls.
see_also: [metric:extraction_quality, module:mod_extract_pymupdf]
---

# Extraktionsqualität prüfen

Dieses Modul beantwortet eine einzige Frage: **Ist der extrahierte Text überhaupt Text?** Es misst nicht die Qualität der Arbeit, sondern die Qualität der Datengrundlage.

Der Anlass ist ein reales Ergebnis aus der Vorarbeit: In einer Stichprobe von 80 Hochschularbeiten lieferten 4 Dateien reinen Zeichenmüll – ältere LaTeX-PDFs mit defekter Glyphenzuordnung, rund 600.000 Zeichen scheinbar gültiger Text. Keine Extraktionsbibliothek meldet das als Fehler, und alle nachgelagerten Metriken werden anschließend anstandslos berechnet. Ohne diese Prüfung wären solche Zeilen von echten Arbeiten nicht zu unterscheiden.

## Verfahren

Aus dem Textanfang (die ersten 5.000 Wortvorkommen genügen) wird der **Anteil sehr häufiger Funktionswörter** bestimmt – rund 30 deutsche und englische Wörter wie „der", „die", „und", „mit", `the`, `of`, `and`. Echter Text in einer dieser Sprachen besteht zu einem stabilen Anteil aus solchen Wörtern; Zeichenmüll enthält sie praktisch nie.

Die Schwelle liegt bei **0,10**. Sie stammt nicht aus der Literatur, sondern aus der Vorarbeit an der genannten Stichprobe: sauberer Text lag bei 0,149 und darüber, Zeichenmüll bei 0,063 und darunter. Zwischen beiden Gruppen liegt also eine breite Lücke, und die Schwelle sitzt in ihrer Mitte.

Werden weniger als 200 Wortvorkommen gefunden, wird **nicht geurteilt**: das Ergebnis ist `sparse`.

## Ergebnis

Die einzelne Metrik [extraction_quality](metric:extraction_quality) mit einem der Werte `ok`, `garbled` oder `sparse`. Der gemessene Anteil selbst wird in den lokalen Lauf-Notizen abgelegt und verlässt das Gerät nie.

## Einschränkungen

**Die Prüfung ist auf Deutsch und Englisch zugeschnitten.** Die Wortliste enthält nur deutsche und englische Funktionswörter. Eine einwandfrei extrahierte französische oder spanische Arbeit sieht für dieses Modul wie Zeichenmüll aus. Bei einem Korpus, das nicht überwiegend deutsch- oder englischsprachig ist, ist `garbled` daher zuerst gegen [language_code](metric:language_code) zu prüfen.

**`garbled` blockiert nichts.** Eine als Zeichenmüll erkannte Arbeit wird vollständig weiter ausgewertet, und alle ihre Zahlen erscheinen in der Tabelle; die Zeile erhält lediglich das Warnzeichen `[!]`. Das ist Absicht – die Entscheidung, was mit solchen Zeilen geschieht, gehört in die Auswertung, nicht in das Werkzeug. Praktische Folge: **vor jeder inhaltlichen Aussage auf `extraction_quality = ok` filtern.**

**`sparse` heißt „nicht beurteilt", nicht „in Ordnung".** Sehr kurze Dokumente – Poster, Deckblatt-Auszüge, Scans ohne Texterkennung – bekommen dieses Ergebnis. Sie können sauber oder unbrauchbar sein; dieses Modul weiß es nicht.
