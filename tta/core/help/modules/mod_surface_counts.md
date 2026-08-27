---
slug: mod_surface_counts
title: Umfang und Satzlängen zählen
kind: module
consumes: [tokens]
produces_artefacts: []
produces_metrics: [word_count, char_count_alpha, sentence_count, avg_word_len, avg_sentence_len, std_sentence_len]
applicability: Läuft, sobald die Zerlegung (`tokens`) vorliegt. Entfällt, wenn die Zerlegung entfallen ist oder kein einziges Wort enthält.
see_also: [module:mod_tokenize, metric:word_count, metric:avg_sentence_len, concept:length_confound, concept:metric_redundancy]
---

# Umfang und Satzlängen zählen

Dieses Modul zählt. Es enthält keine Statistik und keine Heuristik, nur Arithmetik über die Zerlegung aus [mod_tokenize](module:mod_tokenize) – und hat deshalb selbst nichts, was schiefgehen kann. Alles, was an seinen Zahlen fragwürdig ist, kommt aus der Zerlegung.

## Drei Festlegungen

Sie klingen technisch, entscheiden aber, was die Zahlen bedeuten:

- Ein **Wort** ist ein Token mit mindestens einem Buchstaben. Reine Satzzeichen und reine Zahlen zählen nicht mit: `3.14` und `[12]` sind keine Wörter.
- Die **Wortlänge** zählt nur Buchstaben, keine Ziffern und keine Bindestriche.
- Die **Satzlänge** wird in Wörtern gemessen, nicht in Zeichen.

Diese Festlegungen sind der Grund, warum [word_count](metric:word_count) nicht mit der Wortzahl übereinstimmt, die ein Textverarbeitungsprogramm anzeigt – und auch nicht mit der Wortzahl, die intern in [flesch_reading_ease](metric:flesch_reading_ease) eingeht.

## Ergebnis

| Metrik | Bedeutung |
|---|---|
| [word_count](metric:word_count) | Zahl der Wörter |
| [char_count_alpha](metric:char_count_alpha) | Zahl der Buchstaben |
| [sentence_count](metric:sentence_count) | Zahl der Sätze |
| [avg_word_len](metric:avg_word_len) | Buchstaben je Wort |
| [avg_sentence_len](metric:avg_sentence_len) | Wörter je Satz |
| [std_sentence_len](metric:std_sentence_len) | Streuung der Satzlänge |

Die Streuung ist die Standardabweichung über alle Sätze der Arbeit (als vollständige Grundgesamtheit gerechnet, nicht als Stichprobe); bei genau einem Satz ist sie 0.

## Was zu beachten ist

**Die drei Zählungen sind fast dieselbe Zahl.** Wortzahl, Buchstabenzahl und Satzzahl steigen gemeinsam mit dem Umfang der Arbeit; sie messen im Wesentlichen ihre Länge. Für einen Umfangsvergleich genügt **eine** davon – siehe [Redundanz zwischen Metriken](concept:metric_redundancy).

**Die drei Mittelwerte hängen an der Satzerkennung.** Über-Trennung an Abkürzungen und in Literaturverzeichnissen erzeugt kurze Pseudo-Sätze: [sentence_count](metric:sentence_count) wird zu hoch, [avg_sentence_len](metric:avg_sentence_len) zu niedrig, [std_sentence_len](metric:std_sentence_len) zu hoch. Der Fehler ist nicht gleichmäßig, sondern wächst mit der Zitierdichte.

**Der Umfang verzerrt Vergleiche.** Wortzahlen von Hochschularbeiten reichen von wenigen Tausend bis über 80.000 – eine Spannweite, die viele Verhältniszahlen mitzieht. Siehe [Längenabhängigkeit von Metriken](concept:length_confound).
