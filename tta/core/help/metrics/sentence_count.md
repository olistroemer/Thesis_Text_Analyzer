---
slug: sentence_count
title: Sätze
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
references: [kiss2006]
see_also: [module:mod_tokenize, metric:avg_sentence_len, metric:std_sentence_len, metric:word_count]
---

# Sätze (`sentence_count`)

Die Zahl der Sätze, die die Satzerkennung in der Arbeit gefunden hat. Gezählt werden nur Sätze, in denen mindestens ein Wort steht.

## Wie man den Wert liest

**Mit deutlich mehr Vorsicht als die Wortzahl.** Wörter zu zählen ist einfach; Satzgrenzen zu erkennen ist eine Entscheidung, und sie wird von einem vortrainierten statistischen Modell getroffen [@kiss2006], das auf Zeitungstext der 1990er Jahre gelernt hat und nicht auf wissenschaftlicher Prosa. Der Fehler geht überwiegend in **eine** Richtung – zu viele Sätze:

- Abkürzungen, die in Zeitungstext selten sind, beenden hier fälschlich einen Satz. „Siehe Abb. 3.2 sowie Tab. 4." wird zu drei Sätzen.
- **Literaturverzeichnisse sind der Extremfall.** Autoreninitialen und Jahreszahlen in Klammern sehen wie Satzgrenzen aus; zwei Literaturangaben ergeben neun „Sätze" von je einem bis vier Wörtern.

Damit trägt das Literaturverzeichnis weit überproportional zu dieser Zahl bei – **und zwar proportional zur Zahl der Literaturangaben**. Eine zitierfreudige Arbeit hat auf dieser Metrik einen systematischen Zuschlag, der nichts mit ihrem Satzbau zu tun hat.

In der Gegenrichtung wirkt ein kleinerer Effekt: Überschriften haben kein Satzzeichen und verschmelzen mit dem folgenden Satz.

## Verwendung

Als eigenständige Größe ist die Satzzahl wenig aussagekräftig – sie ist im Kern ein weiteres Umfangsmaß und läuft mit [word_count](metric:word_count) mit. Ihre Bedeutung liegt darin, dass sie **Nenner** von [avg_sentence_len](metric:avg_sentence_len) und Grundlage von [std_sentence_len](metric:std_sentence_len) ist: Die genannte Über-Trennung drückt die eine und treibt die andere.

Ein grober Selbsttest, wenn Satzlängen ausgewertet werden sollen: den Anteil abschätzen, den das Literaturverzeichnis an dieser Zahl hat. Das ist eine billige Prüfung und in diesem Projekt bislang nicht durchgeführt.
