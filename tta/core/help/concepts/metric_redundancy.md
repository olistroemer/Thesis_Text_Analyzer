---
slug: metric_redundancy
title: Redundanz zwischen Metriken
kind: concept
see_also: [metric:avg_word_len, metric:flesch_reading_ease, metric:ttr, metric:bigram_repetition_rate, concept:length_confound]
---

# Redundanz zwischen Metriken

Das Werkzeug zeigt 31 Metriken. Sie messen keine 31 verschiedenen Dinge. Mehrere Paare laufen so eng zusammen, dass sie praktisch dieselbe Zahl sind – und wer beide berichtet, berichtet einen Befund zweimal und lässt ihn dadurch gewichtiger erscheinen, als er ist.

## Die belegten Paare

An einer Stichprobe von 80 Hochschularbeiten zeigte sich in **beiden** untersuchten Sprachen dasselbe Muster, jeweils mit einem Betrag der Korrelation von 0,9 oder darüber:

| Paar | Warum |
|---|---|
| [avg_word_len](metric:avg_word_len) und [flesch_reading_ease](metric:flesch_reading_ease) | Die Wortlänge steckt über die Silbenzahl direkt in der Lesbarkeitsformel. |
| [bigram_repetition_rate](metric:bigram_repetition_rate) und [trigram_repetition_rate](metric:trigram_repetition_rate) | Dasselbe Maß über Folgen unterschiedlicher Länge. |
| [ttr](metric:ttr) und [hapax_token_ratio](metric:hapax_token_ratio) | Beide teilen eine Wortschatzgröße durch die Gesamtwortzahl und sinken deshalb gemeinsam mit der Länge. |
| [word_count](metric:word_count) und [char_count_alpha](metric:char_count_alpha) | Zwei Schreibweisen desselben Umfangs. |

Ein weiteres Paar wurde vor der Umsetzung geprüft und deshalb gar nicht aufgenommen: Wortentropie lief mit [yules_k](metric:yules_k) bei einem Betrag der Korrelation um 0,92 mit und ist daher nie eine Metrik dieses Werkzeugs geworden (ADR-0011).

Die Stichprobe war klein (80 Arbeiten, darunter 4 unbrauchbare Extraktionen). Dass diese Paare zusammenlaufen, ist aber nicht nur ein Befund der Stichprobe: In jedem Fall gibt es einen rechnerischen Grund dafür, wie die rechte Spalte zeigt. Deshalb ist der Zusammenhang zu erwarten und nicht als Zufall abzutun.

## Warum dann alle mitgeliefert werden

Weil die Auswahl an echten Daten getroffen werden soll und nicht vorab. Vier Zahlen zu erheben und drei später zu verwerfen ist billig; eine im Voraus zu verwerfen und sie später zu brauchen ist teuer, weil dann der ganze Bestand neu ausgewertet werden muss. Aus demselben Grund gibt es zwei Einmalwort-Varianten und drei Wortschatzmaße.

Die Erhebung ist also absichtlich redundant. **Die Auswertung darf es nicht sein.**

## Was daraus folgt

**Aus jedem Paar eine wählen und die Wahl begründen.** Vorschlag, nach Belastbarkeit:

- Wortlänge oder Lesbarkeit: **[avg_word_len](metric:avg_word_len)**, weil es keine Silbenschätzung braucht und für Deutsch nicht durch die Trennstellenzählung verzerrt ist.
- Wortpaare oder Wortdrillinge: **[bigram_repetition_rate](metric:bigram_repetition_rate)**, weil es weniger von der Über-Trennung durch die Satzerkennung betroffen ist.
- Wortschatz: **[yules_k](metric:yules_k)**, als längenstabilstes der drei Maße ([Längenabhängigkeit von Metriken](concept:length_confound)).
- Umfang: **[word_count](metric:word_count)**, als anschaulichstes.

**Nicht zwei Metriken eines Paares als unabhängige Belege behandeln.** Zwei Metriken, die dasselbe messen, bestätigen einander nicht. „Sowohl die Wortlänge als auch die Lesbarkeit zeigen den Effekt" ist eine Aussage, nicht zwei.

**Und erst recht nicht: eine gegen die andere rechnen.** Ein Zusammenhang zwischen [avg_word_len](metric:avg_word_len) und [flesch_reading_ease](metric:flesch_reading_ease) ist keine Entdeckung – er ist die Formel.
