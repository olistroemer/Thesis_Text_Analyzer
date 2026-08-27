---
slug: word_count
title: Wörter
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_surface_counts, metric:char_count_alpha, metric:n_pages, concept:length_confound, concept:metric_redundancy]
---

# Wörter (`word_count`)

Die Zahl der Wörter der Arbeit, gezählt von [mod_surface_counts](module:mod_surface_counts) über die Zerlegung aus [mod_tokenize](module:mod_tokenize).

Als **Wort** gilt dabei ein Token mit mindestens einem Buchstaben. Reine Zahlen und Satzzeichen zählen nicht: In „Der Mittelwert war 3,14 s, siehe [12]." zählen `3,14` und `12` nicht mit. Das ist eine Festlegung, keine Selbstverständlichkeit – und der Grund, warum dieser Wert von der Wortzahl einer Textverarbeitung abweicht und auch von der Wortzahl, die intern in [flesch_reading_ease](metric:flesch_reading_ease) eingeht.

## Wie man den Wert liest

Als das **belastbarste Umfangsmaß** dieses Werkzeugs – belastbarer als [n_pages](metric:n_pages), das von Satzspiegel und Vorlage abhängt, und als [file_size_bytes](metric:file_size_bytes), das an der Bebilderung hängt.

Zwei Einschränkungen:

**Gezählt wird alles.** Kopf- und Fußzeilen jeder Seite, Inhaltsverzeichnis, Bildunterschriften, Tabelleninhalte und das gesamte Literaturverzeichnis sind mitgezählt; der extrahierte Text unterscheidet sie nicht vom Fließtext. Eine Arbeit mit 40 Seiten Tabellenanhang hat eine entsprechend höhere Wortzahl, ohne mehr geschrieben zu haben.

**Am Zeilenende getrennte Wörter zählen doppelt.** Die Extraktion macht aus einem getrennten Wort zwei Bruchstücke. Wie häufig das ist, hängt am erzeugenden Programm ([producer_category](metric:producer_category)), nicht an der Arbeit – bei einem Blocksatz-Dokument aus LaTeX also häufiger.

## Rolle in der Auswertung

Diese Zahl ist die wichtigste **Kontrollgröße** des Werkzeugs. Ein großer Teil der Verhältnismetriken – vor allem [ttr](metric:ttr) und [hapax_token_ratio](metric:hapax_token_ratio) – hängt rechnerisch am Umfang. In der Vorarbeit zeigten 5 von 16 Metriken bei englischen und 7 von 16 bei deutschen Arbeiten einen Betrag der Korrelation über 0,5 mit dieser Zahl. Siehe [Längenabhängigkeit von Metriken](concept:length_confound).

Zusammen mit [char_count_alpha](metric:char_count_alpha) und [sentence_count](metric:sentence_count) bildet sie eine Gruppe fast deckungsgleicher Größen; für einen Umfangsvergleich genügt eine davon ([Redundanz zwischen Metriken](concept:metric_redundancy)).
