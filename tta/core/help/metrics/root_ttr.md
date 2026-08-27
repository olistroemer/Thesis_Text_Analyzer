---
slug: root_ttr
title: Wortschatzreichtum (Guiraud)
kind: metric
produced_by: mod_vocabulary
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
references: [guiraud1954]
see_also: [module:mod_vocabulary, metric:ttr, metric:yules_k, concept:length_confound, concept:cross_language_comparison]
---

# Wortschatzreichtum (Guiraud) (`root_ttr`)

Die Zahl verschiedener Wörter, geteilt durch die **Wurzel** der Gesamtwortzahl – der Guiraud-Index [@guiraud1954].

## Warum die Wurzel

Sie ist ein Gegenmittel gegen das Grundproblem von [ttr](metric:ttr). Dort sinkt der Wert bei jedem Text mit zunehmender Länge, weil verschiedene Wörter langsamer zunehmen als die Gesamtwortzahl. Guiraud nimmt an, dass sie ungefähr wie die Wurzel zunehmen, und teilt entsprechend – der Längeneffekt wird dadurch weitgehend, aber nicht vollständig herausgerechnet.

Praktisch heißt das: **Von den beiden einfachen Wortschatzmaßen ist dies das brauchbarere.** Ein Vergleich zwischen Bachelor- und Masterarbeiten ist hier eher zulässig als bei TTR.

## Wie man den Wert liest

Nur **relativ, innerhalb eines Korpus**. Der Betrag hat keine Bedeutung, die sich außerhalb dieses Werkzeugs deuten ließe: Er ist keine Zahl zwischen 0 und 1 und keine Größe mit einer etablierten Skala; er wächst mit der Wortzahl, wenn auch schwach.

Vollständig ist der Längeneffekt **nicht** beseitigt. Die Wurzelannahme ist eine Näherung, und bei den sehr großen Längenunterschieden von Hochschularbeiten bleibt ein Rest. Bei starken Umfangsunterschieden bleibt [yules_k](metric:yules_k) das stabilere Maß; siehe [Längenabhängigkeit von Metriken](concept:length_confound).

Es bleibt bei allem, was schon für TTR gilt: keine Grundformenbildung, und **kein Vergleich über Sprachgrenzen** – deutsche Komposita und deutsche Flexion heben den Wert aus grammatischen Gründen ([Vergleich über Sprachgrenzen](concept:cross_language_comparison)).
