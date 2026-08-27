---
slug: bigram_repetition_rate
title: Wiederholte Wortpaare
kind: metric
produced_by: mod_redundancy
applicability: Vorhanden, sobald mindestens ein Satz zwei Wörter enthält; sonst entfällt die Berechnung.
see_also: [module:mod_redundancy, metric:trigram_repetition_rate, metric:sentence_count, concept:metric_redundancy]
---

# Wiederholte Wortpaare (`bigram_repetition_rate`)

Der Anteil der **Wortpaare**, die in der Arbeit mehr als einmal vorkommen. Ein Wortpaar ist jede Folge zweier unmittelbar aufeinanderfolgender Wörter: „in dieser", „dieser Arbeit", „Arbeit wird".

    Wiederholungsrate = 1 - (verschiedene Paare / alle Paare)

Der Wert liegt zwischen 0 (kein Paar kommt zweimal vor) und knapp unter 1. Wortpaare werden **nicht über Satzgrenzen hinweg** gebildet.

## Wie man den Wert liest

Als Stellvertreter für **formelhaftes Schreiben** – ein Signal, das bei der Frage nach maschinellem Einfluss von Interesse ist, weil sprachliche Gleichförmigkeit als eines seiner Merkmale gilt.

Aber: Ein hoher Wert bedeutet ebenso gut **fachliche Präzision**. Der wiederholte Name des Untersuchungsgegenstands, wiederkehrende Verweise („siehe Abbildung", „in Kapitel"), die Standardwendungen wissenschaftlichen Schreibens und ein Literaturverzeichnis mit demselben Verlag in 50 Einträgen erzeugen alle Wiederholung. Die Zahl unterscheidet Armut des Ausdrucks nicht von Konsistenz der Terminologie.

## Die Verzerrung, die man kennen muss

Weil Wortpaare an Satzgrenzen abbrechen, **entfernt jede überzählige Satzgrenze legitime Wortpaare**. Die Satzerkennung trennt bei Abkürzungen und in Literaturverzeichnissen zu häufig – der gemessene Wert fällt also, und zwar **proportional zur Zitierdichte**.

Praktische Folge: Eine gründlich referenzierende Arbeit erscheint weniger wiederholend als eine sonst gleiche mit weniger Belegen. Ein Vergleich zitierdichter mit zitierarmen Arbeiten auf dieser Metrik ist deshalb nicht zulässig, ohne dies zu kontrollieren.

## Verhältnis zur Drillingsrate

[trigram_repetition_rate](metric:trigram_repetition_rate) läuft fast deckungsgleich mit (Betrag der Korrelation 0,9 oder darüber in beiden Sprachen). Für eine Auswertung ist **eine** der beiden zu wählen; siehe [Redundanz zwischen Metriken](concept:metric_redundancy).
