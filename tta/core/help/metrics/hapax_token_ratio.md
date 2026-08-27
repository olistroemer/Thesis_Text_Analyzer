---
slug: hapax_token_ratio
title: Einmalwörter (an Tokens)
kind: metric
produced_by: mod_vocabulary
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_vocabulary, metric:hapax_type_ratio, metric:ttr, concept:length_confound]
---

# Einmalwörter (an Tokens) (`hapax_token_ratio`)

Der Anteil der **Einmalwörter** an allen Wörtern der Arbeit. Ein Einmalwort (in der Fachliteratur *Hapax legomenon*) ist ein Wort, das im ganzen Text genau einmal vorkommt.

Der Gedanke: Wer viele Wörter nur ein einziges Mal benutzt, greift breiter in den Wortschatz. Einmalwörter gelten als der empfindlichste Teil des Wortschatzprofils – dort zeigen sich Fachbegriffe, Eigennamen und selten benutzte Wörter.

## Wie man den Wert liest

**Mit derselben Vorsicht wie [ttr](metric:ttr), aus demselben Grund.** Der Nenner ist die Gesamtwortzahl, und Einmalwörter nehmen mit der Textlänge viel langsamer zu als der Text selbst. Der Wert sinkt also systematisch mit dem Umfang – in der Vorarbeit lief er so eng mit TTR mit (Betrag der Korrelation 0,9 oder darüber), dass beide Zahlen nebeneinander dasselbe berichten.

Für einen Vergleich zwischen Arbeiten unterschiedlicher Länge ist deshalb entweder auf die Länge zu kontrollieren oder auf ein längenstabiles Maß zu wechseln ([yules_k](metric:yules_k)). Siehe [Längenabhängigkeit von Metriken](concept:length_confound).

## Warum es zwei Einmalwort-Metriken gibt

[hapax_type_ratio](metric:hapax_type_ratio) misst dasselbe mit einem anderen Nenner: Anteil am **Wortschatz** statt am Text. Die beiden verhalten sich bei wachsender Textlänge unterschiedlich, und welche sich an echten Arbeitskorpora besser bewährt, soll dieses Projekt herausfinden statt voraussetzen. Beide werden daher erhoben; für eine Auswertung ist eine zu wählen.

## Eine technische Verunreinigung

Am Zeilenende getrennte Wörter überleben die Extraktion als zwei Bruchstücke, die im übrigen Text nie wieder vorkommen – also als **zwei zusätzliche Einmalwörter**. Diese Metrik ist damit die anfälligste für diesen Fehler, und er hängt am erzeugenden Programm ([producer_category](metric:producer_category)), nicht an der Arbeit.
