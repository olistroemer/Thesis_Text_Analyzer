---
slug: avg_word_len
title: Mittlere Wortlänge
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_surface_counts, metric:char_count_alpha, metric:flesch_reading_ease, concept:cross_language_comparison, concept:metric_redundancy, concept:outlier_detection]
---

# Mittlere Wortlänge (`avg_word_len`)

Buchstaben je Wort: [char_count_alpha](metric:char_count_alpha) geteilt durch [word_count](metric:word_count).

## Warum diese Metrik zählt

Sie ist eine der **vier längenstabilen** Metriken dieses Werkzeugs – die einzigen, die man zwischen einer 8.000-Wort-Bachelorarbeit und einer 60.000-Wort-Masterarbeit überhaupt vergleichen darf. In der Vorarbeit lag ihr Betrag der Korrelation mit der Wortzahl in beiden Sprachen unter 0,3. Deshalb gehört sie zu den vier Metriken, deren Abweichung von der Referenz im Bericht am meisten sagt ([Ausreißererkennung](concept:outlier_detection)).

Inhaltlich ist sie ein Stellvertreter für **nominalen, fachsprachlichen Stil**: längere Wörter bedeuten meist mehr Fachbegriffe und mehr Substantivierung.

## Was man daraus nicht schließen darf

**Sie sagt fast dasselbe wie [flesch_reading_ease](metric:flesch_reading_ease).** In der Vorarbeit lag der Betrag der Korrelation der beiden in beiden Sprachen bei 0,9 oder darüber – nicht überraschend, denn die Wortlänge ist über die Silbenzahl direkt in die Lesbarkeitsformel eingebaut. Beide zu berichten heißt, dasselbe zweimal zu berichten ([Redundanz zwischen Metriken](concept:metric_redundancy)).

**Sie trennt nicht, wofür sie am ehesten herangezogen wird.** In der Vorarbeit lagen englische Hochschularbeiten mit einem Median von 5,07 näher an der Verteilung maschinell erzeugter Texte einer Vergleichsstudie (Mittel 4,96) als an deren menschlich geschriebenen Texten (Mittel 4,40). Zwei Lesarten sind gleich gut möglich: Akademische Formalsprache hat dieselben oberflächlichen Merkmale wie maschinell erzeugte Formalsprache – oder der Einfluss ist im Korpus schon vorhanden. **Aus dieser Metrik allein ist zwischen beidem nicht zu entscheiden.** Sie taugt nicht als Nachweis maschinellen Einflusses.

**Sprachen sind nicht vergleichbar.** Deutsche Werte liegen deutlich höher (in der Vorarbeit 6,15 gegenüber 5,07), weil Komposita ein Wort bleiben. Das ist Grammatik, kein Stil: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).

**Am Zeilenende getrennte Wörter senken den Wert**, und das hängt am erzeugenden Programm ([producer_category](metric:producer_category)).
