---
slug: mod_redundancy
title: Wortwiederholungen messen
kind: module
consumes: [tokens]
produces_artefacts: []
produces_metrics: [bigram_repetition_rate, trigram_repetition_rate]
applicability: Läuft, sobald die Zerlegung (`tokens`) vorliegt und mindestens ein Satz zwei Wörter enthält. Sonst lautet das Ergebnis „nicht anwendbar".
see_also: [metric:bigram_repetition_rate, metric:trigram_repetition_rate, module:mod_tokenize, concept:metric_redundancy]
---

# Wortwiederholungen messen

Dieses Modul misst, wie oft sich **kurze Wortfolgen** in einer Arbeit wiederholen: Wortpaare („in dieser") und Wortdrillinge („in dieser Arbeit"). Der Gedanke dahinter ist, dass formelhaftes, wiederholendes Schreiben sich hier zeigen sollte – ein Signal, das bei der Frage nach maschinell erzeugtem Text von Interesse ist.

## Verfahren

Über die kleingeschriebenen Wörter jedes Satzes werden alle aufeinanderfolgenden Paare bzw. Drillinge gebildet. Die Wiederholungsrate ist

    1 - (verschiedene Folgen / alle Folgen)

Der Wert liegt zwischen 0 (keine Folge kommt zweimal vor) und knapp unter 1 (fast alles ist Wiederholung).

Wortfolgen werden **nicht über Satzgrenzen hinweg** gebildet: Das letzte Wort eines Satzes und das erste des nächsten sind kein Paar.

## Ergebnis

- [bigram_repetition_rate](metric:bigram_repetition_rate) – Wiederholungsrate der Wortpaare.
- [trigram_repetition_rate](metric:trigram_repetition_rate) – Wiederholungsrate der Wortdrillinge. Hat ein Text Paare, aber keine Drillinge (nur Zwei-Wort-Sätze), ist der Wert 0.

## Einschränkungen

**Die beiden Zahlen sind fast dieselbe.** In der Vorarbeit lagen Paar- und Drillingsrate in beiden Sprachen bei einem Betrag der Korrelation von 0,9 oder darüber. Beide zu berichten heißt, dasselbe zweimal zu berichten – siehe [Redundanz zwischen Metriken](concept:metric_redundancy). Sie werden dennoch beide erhoben, damit die Wahl zwischen ihnen an echten Korpora getroffen werden kann statt vorab.

**Die Satzerkennung verzerrt nach unten.** Weil Wortfolgen an Satzgrenzen abbrechen, **entfernt** jede überzählige Satzgrenze legitime Wortfolgen. Über-Trennung an Abkürzungen und in Literaturverzeichnissen senkt damit die gemessene Wiederholung – und zwar proportional zur Zitierdichte. Eine zitierfreudige Arbeit erscheint dadurch weniger wiederholend als eine sonst gleiche zitierarme. Das ist die Verzerrung, die bei diesen zwei Metriken am leichtesten zu einer falschen Aussage führt.

**Fachbegriffe treiben den Wert.** Der Name des Untersuchungsgegenstands, wiederkehrende Kapitel- und Abbildungsverweise („siehe Abbildung") und die Standardformeln wissenschaftlichen Schreibens sind ebenfalls Wiederholung. Ein hoher Wert kann fachliche Präzision genauso gut bedeuten wie sprachliche Armut; die Zahl unterscheidet das nicht.
