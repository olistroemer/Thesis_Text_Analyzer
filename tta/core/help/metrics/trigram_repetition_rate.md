---
slug: trigram_repetition_rate
title: Wiederholte Wortdrillinge
kind: metric
produced_by: mod_redundancy
applicability: Vorhanden, sobald Wortpaare gebildet werden konnten; enthält der Text keine Dreierfolge, ist der Wert 0.
see_also: [module:mod_redundancy, metric:bigram_repetition_rate, concept:metric_redundancy]
---

# Wiederholte Wortdrillinge (`trigram_repetition_rate`)

Wie [bigram_repetition_rate](metric:bigram_repetition_rate), nur über Folgen von **drei** aufeinanderfolgenden Wörtern: „in dieser Arbeit", „dieser Arbeit wird". Auch hier wird nicht über Satzgrenzen hinweg gebildet.

## Was die längere Folge hinzufügen soll

Dreierfolgen sind seltener und spezifischer als Paare. Ein wiederholtes Paar kann grammatischer Zufall sein („in der", „und die"); eine wiederholte Dreierfolge ist eher eine bewusst oder unbewusst wiederverwendete Wendung. Die Metrik sollte deshalb näher an „formelhaftem Schreiben" liegen und weniger von der Grammatik der Sprache getrieben sein.

Die absoluten Werte liegen entsprechend niedriger als bei den Paaren: Es gibt mehr Möglichkeiten und damit weniger Wiederholung.

## Was sich in der Vorarbeit gezeigt hat

**Die Unterscheidung trägt in der Praxis kaum.** In beiden untersuchten Sprachen liefen Paar- und Drillingsrate mit einem Betrag der Korrelation von 0,9 oder darüber zusammen. Sie zu berichten ist im Wesentlichen, die Paarrate zweimal zu berichten ([Redundanz zwischen Metriken](concept:metric_redundancy)).

Beide werden dennoch erhoben, damit die Wahl zwischen ihnen an echten, größeren Arbeitskorpora getroffen werden kann statt vorab an einer Stichprobe von 80 Dokumenten.

## Einschränkungen

Es gelten dieselben wie bei den Wortpaaren, teils verstärkt:

- **Über-Trennung durch die Satzerkennung senkt den Wert stärker**, weil eine Dreierfolge zwei Wortübergänge braucht und damit an mehr Stellen zerstört werden kann. Der Fehler wächst mit der Zitierdichte.
- Ein hoher Wert kann fachliche Konsistenz statt sprachlicher Armut bedeuten.
- Der Wert 0 ist bei kurzen oder stark zerteilten Texten eine reale Möglichkeit und bedeutet dann „keine Dreierfolge kam zweimal vor", nicht „völlig wiederholungsfrei".
