---
slug: char_count_alpha
title: Buchstaben
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_surface_counts, metric:word_count, metric:text_chars, metric:avg_word_len, concept:metric_redundancy]
---

# Buchstaben (`char_count_alpha`)

Die Zahl der **Buchstaben** in allen Wörtern der Arbeit. Ziffern, Satzzeichen, Leerzeichen und Bindestriche zählen nicht mit; Umlaute und Eszett zählen als Buchstaben.

Damit ist dieser Wert deutlich kleiner als [text_chars](metric:text_chars), das alle Zeichen des extrahierten Textes zählt – einschließlich Leerzeichen, Zeilenumbrüchen und Formatierungsresten.

## Wie man den Wert liest

Er ist im Wesentlichen **eine andere Schreibweise von [word_count](metric:word_count)**: Beide steigen gemeinsam mit dem Umfang, in der Vorarbeit mit einem Betrag der Korrelation von 0,9 oder darüber. Für einen Umfangsvergleich sollte man sich für eine der beiden entscheiden – die Wortzahl ist die anschaulichere ([Redundanz zwischen Metriken](concept:metric_redundancy)).

Sein eigentlicher Zweck ist ein anderer: Er ist der **Zähler von [avg_word_len](metric:avg_word_len)**. Die mittlere Wortlänge, eine der wenigen längenstabilen Metriken dieses Werkzeugs, ist genau dieser Wert geteilt durch die Wortzahl.

Als eigenständiger Befund ist er kaum brauchbar; als Zwischengröße, deren Definition man kennen muss, um die mittlere Wortlänge zu deuten, ist er nützlich.
