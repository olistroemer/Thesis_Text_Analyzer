---
slug: std_sentence_len
title: Streuung der Satzlänge
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; bei genau einem Satz ist der Wert 0.
see_also: [module:mod_surface_counts, metric:avg_sentence_len, metric:sentence_count, concept:outlier_detection, concept:length_confound]
---

# Streuung der Satzlänge (`std_sentence_len`)

Die Standardabweichung der Satzlängen in Wörtern, gerechnet über alle Sätze der Arbeit als vollständige Grundgesamtheit. Ein niedriger Wert heißt: alle Sätze ähnlich lang. Ein hoher Wert heißt: kurze und lange Sätze wechseln sich ab.

## Warum die Metrik interessant wäre

Der Wechsel von Satzlängen gilt als Merkmal lebendigen Schreibens, und ihre Vereinheitlichung als eines der Merkmale, an denen maschinell erzeugter Text auffallen könnte. Zudem ist die Streuung eine der **vier längenstabilen** Metriken (Betrag der Korrelation mit der Wortzahl unter 0,3 in beiden Sprachen) und damit eine der vier, auf denen der Bericht Ausreißer bestimmt ([Ausreißererkennung](concept:outlier_detection)).

## Warum sie in diesem Werkzeug nicht das misst

Bei Hochschularbeiten liegt sie bei etwa 12 bis 15, gegenüber ungefähr 6 bis 10 in einem Korpus aus Aufsätzen. Dieser Unterschied ist **kein Stilunterschied**. Er entsteht daraus, dass der extrahierte Text nicht aus Prosa besteht, sondern aus Prosa **plus** Bildunterschriften, Tabellenzellen, Formelfragmenten, Programmcode, Überschriften und dem Literaturverzeichnis – alles unmarkiert, alles mit vollem Gewicht, und alles mit extremen Längen in beide Richtungen. Dazu kommen die Pseudo-Sätze der Satzerkennung, die den Wert weiter treiben.

**Auf rohem, aus PDF extrahiertem Text kann diese Metrik Schreibstil und Layoutartefakt nicht trennen.** Wer sie ernsthaft nutzen will, muss den Fließtext vorher bereinigen – Literaturverzeichnis, Code und Bildunterschriften entfernen –, oder das hohe Grundrauschen ausdrücklich als Grenze der Aussage benennen.

## Wie man sie dennoch benutzt

Als **Rangordnung innerhalb eines Korpus** technisch ähnlicher Arbeiten, nicht als absolute Zahl. Und mit einem Blick auf die Struktur: Ein sehr hoher Wert bedeutet meist einen großen Anhang oder ein umfangreiches Literaturverzeichnis, nicht abwechslungsreiches Schreiben.
