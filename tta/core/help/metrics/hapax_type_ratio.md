---
slug: hapax_type_ratio
title: Einmalwörter (an Typen)
kind: metric
produced_by: mod_vocabulary
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_vocabulary, metric:hapax_token_ratio, metric:yules_k, concept:length_confound]
---

# Einmalwörter (an Typen) (`hapax_type_ratio`)

Der Anteil der Einmalwörter am **Wortschatz** – also an der Zahl der verschiedenen Wörter, nicht an der Gesamtwortzahl. Der Wert antwortet auf die Frage: *Wie viel Prozent der von dieser Arbeit benutzten Wörter kommen nur ein einziges Mal vor?*

Bei natürlichem Text liegt die Antwort erfahrungsgemäß hoch – ein großer Teil jedes Wortschatzes besteht aus Wörtern, die genau einmal auftreten.

## Verhältnis zur Schwestermetrik

[hapax_token_ratio](metric:hapax_token_ratio) hat denselben Zähler und einen anderen Nenner. Der Unterschied ist keine Spielerei:

- **Am Text gemessen** (Schwestermetrik) sinkt der Wert stark mit der Länge – der Text wächst schneller als sein Wortschatz.
- **Am Wortschatz gemessen** (diese Metrik) ist der Längeneffekt schwächer, weil Zähler und Nenner beide Wortschatzgrößen sind. Ganz verschwindet er nicht: Mit wachsendem Text bekommen zuvor einmalige Wörter eine zweite Gelegenheit vorzukommen, sodass ihr Anteil am Wortschatz langsam sinkt.

Beide werden absichtlich mitgeliefert, damit die Wahl zwischen ihnen an echten Arbeitskorpora getroffen wird statt vorab. Für eine Auswertung ist **eine** zu nehmen; beide zu berichten wäre eine Doppelung.

## Wie man den Wert liest

Als Aussage über die **Form der Häufigkeitsverteilung**: Ein hoher Anteil bedeutet einen Wortschatz aus vielen Gelegenheitswörtern über einem kleinen Kern häufig wiederholter Wörter.

Zu beachten bleibt: keine Grundformenbildung („Untersuchung" und „Untersuchungen" sind zwei Typen, jeder möglicherweise einmalig), keine Vergleichbarkeit über Sprachgrenzen, und die Verunreinigung durch am Zeilenende getrennte Wörter, die als zusätzliche Einmalwörter erscheinen. Wer ein Wortschatzmaß mit den geringsten Vorbehalten sucht, nimmt [yules_k](metric:yules_k).
