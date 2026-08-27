---
slug: ttr
title: Wortschatzreichtum (TTR)
kind: metric
produced_by: mod_vocabulary
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_vocabulary, metric:root_ttr, metric:yules_k, metric:word_count, concept:length_confound, concept:cross_language_comparison]
---

# Wortschatzreichtum (TTR) (`ttr`)

Das Verhältnis **verschiedener Wörter zu allen Wörtern**: Enthält eine Arbeit 30.000 Wörter, darunter 4.500 verschiedene, ist der Wert 0,15. Groß- und Kleinschreibung werden zusammengezogen; „Untersuchung" und „untersuchung" sind ein Wort.

## Die entscheidende Warnung

**TTR ist bei Hochschularbeiten eher ein Längenmaß als ein Wortschatzmaß.**

Der Grund ist rechnerisch und unvermeidbar: Je länger ein Text wird, desto mehr Wörter wiederholen sich zwangsläufig, weil die Zahl der verfügbaren Wörter einer Sprache begrenzt ist. Der Wert sinkt also mit der Länge – bei **jedem** Text, unabhängig davon, wie reich sein Wortschatz ist. Bei Hochschularbeiten, deren Umfang von wenigen Tausend bis über 80.000 Wörtern reicht, überdeckt dieser Effekt den eigentlichen Unterschied.

Praktische Folge: **Eine Bachelorarbeit hat einen höheren TTR als eine Masterarbeit, fast unabhängig vom Wortschatz beider.** Ein Vergleich der beiden Gruppen auf dieser Metrik vergleicht ihre Länge. Ausführlich: [Längenabhängigkeit von Metriken](concept:length_confound).

## Was stattdessen zu verwenden ist

- [root_ttr](metric:root_ttr) – dieselbe Idee, durch die Wurzel der Wortzahl geteilt und damit deutlich längenrobuster.
- [yules_k](metric:yules_k) – nutzt die gesamte Häufigkeitsverteilung und ist das längenstabilste Wortschatzmaß dieses Werkzeugs.

TTR wird dennoch mitgeliefert: Es ist das bekannteste und am häufigsten berichtete Maß, und ohne es lässt sich der Bezug zur Literatur und zu anderen Studien nicht herstellen. Es steht hier, damit man es **vergleichen** kann – nicht, damit man darauf schließt.

## Weitere Einschränkungen

- **Sprachen sind nicht vergleichbar.** Deutsche Werte liegen weit höher (in der Vorarbeit 0,20 gegenüber 0,12), weil Komposita jeweils ein eigenes Wort sind und die Flexion mehr Formen erzeugt. Das ist Grammatik, kein Stil: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).
- **Keine Grundformen.** „Untersuchung" und „Untersuchungen" sind zwei verschiedene Wörter.
- [hapax_token_ratio](metric:hapax_token_ratio) verhält sich fast identisch (Betrag der Korrelation 0,9 oder darüber); beide zu berichten ist eine Doppelung.
