---
slug: yules_k
title: Wortschatzreichtum (Yules K)
kind: metric
produced_by: mod_vocabulary
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
references: [yule1944, zipf1949]
see_also: [module:mod_vocabulary, metric:ttr, metric:root_ttr, concept:length_confound, concept:outlier_detection, concept:cross_language_comparison]
---

# Wortschatzreichtum (Yules K) (`yules_k`)

Yules Charakteristik K [@yule1944] misst, wie stark eine Arbeit dazu neigt, **Wörter zu wiederholen**. Ein **hoher** Wert bedeutet viel Wiederholung, also einen engeren Wortschatz; ein **niedriger** Wert bedeutet breiteren Wortgebrauch. Das ist die umgekehrte Richtung zu [ttr](metric:ttr) und zu den Einmalwort-Anteilen – der häufigste Lesefehler bei dieser Spalte.

## Wie es gerechnet wird

Anders als die übrigen Wortschatzmaße zählt K nicht nur Wörter und Wortformen, sondern nutzt die **gesamte Häufigkeitsverteilung**: Für jede Häufigkeit wird gezählt, wie viele Wörter genau so oft vorkommen, und dieser Beitrag geht quadratisch gewichtet ein. Wenige sehr häufige Wörter treiben den Wert daher stark.

    K = 10.000 * (Summe über i von i^2 * V_i  -  N) / N^2

Dabei ist N die Gesamtwortzahl und V_i die Zahl der Wörter, die genau i-mal vorkommen. Der Faktor 10.000 bringt das Ergebnis in einen gut lesbaren Zahlenbereich.

Weil die Formel eine **Eigenschaft der Verteilung** und nicht ein Verhältnis zweier mitwachsender Zählungen erfasst, ist sie gegenüber der Textlänge weitgehend stabil – genau die Eigenschaft, die den einfachen Maßen fehlt. Zugrunde liegt, dass Worthäufigkeiten in natürlicher Sprache einer regelhaften Verteilung folgen [@zipf1949].

## Warum das die belastbarste Wortschatzmetrik ist

Sie gehört zu den **vier längenstabilen** Metriken dieses Werkzeugs: In der Vorarbeit lag der Betrag ihrer Korrelation mit der Wortzahl in beiden Sprachen unter 0,3. Damit ist sie die einzige Wortschatzmetrik, die man zwischen Arbeiten sehr unterschiedlichen Umfangs vergleichen darf, und sie ist eine der vier Metriken, auf denen der Bericht Ausreißer bestimmt ([Ausreißererkennung](concept:outlier_detection)).

Wenn eine einzige Wortschatzzahl berichtet werden soll, ist es diese. [ttr](metric:ttr) und [root_ttr](metric:root_ttr) stehen daneben, um den Bezug zur Literatur herstellen zu können – nicht, weil sie besser wären.

## Grenzen

- **Der Betrag ist nicht deutbar.** K hat keine Skala mit einer inhaltlichen Bedeutung. Brauchbar sind Ränge und Verteilungen innerhalb eines Korpus, nicht der Wert selbst.
- **Kein Vergleich über Sprachgrenzen.** Deutsche Komposita und deutsche Flexion verändern die Häufigkeitsverteilung grundlegend: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).
- **Fachbegriffe treiben den Wert.** Der ständig wiederholte Name des Untersuchungsgegenstands wirkt wie sprachliche Armut. Ein hoher Wert kann fachliche Enge des Themas bedeuten – nicht Enge des Ausdrucks.
- Sie erbt die Verunreinigung durch am Zeilenende getrennte Wörter ([producer_category](metric:producer_category)).
