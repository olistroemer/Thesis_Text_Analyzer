---
slug: length_confound
title: Längenabhängigkeit von Metriken
kind: concept
see_also: [metric:word_count, metric:ttr, metric:yules_k, metric:root_ttr, concept:metric_redundancy, concept:outlier_detection]
---

# Längenabhängigkeit von Metriken

Die meisten Verhältniszahlen dieses Werkzeugs verändern sich **systematisch mit dem Umfang eines Textes** – auch dann, wenn sich am Schreiben nichts ändert. Wer das nicht berücksichtigt, vergleicht am Ende Längen und hält es für einen Befund über Sprache. Es ist die wichtigste einzelne Fehlerquelle bei der Auswertung dieser Daten.

## Warum es passiert

Am Beispiel des Wortschatzes: Ein Text kann nur begrenzt viele verschiedene Wörter enthalten, denn eine Sprache hat begrenzt viele. Je länger ein Text wird, desto häufiger muss er Wörter wiederholen. Die Zahl **verschiedener** Wörter wächst also langsamer als die Zahl **aller** Wörter – und jedes Verhältnis der beiden sinkt mit der Länge, bei jedem Text, unabhängig von seiner sprachlichen Qualität.

Dasselbe Muster in anderer Gestalt trifft Anteile von Einmalwörtern, Wiederholungsraten von Wortfolgen und jede Größe, deren Nenner mit dem Text mitwächst.

## Warum es bei Hochschularbeiten schlimmer ist als sonst

Das ist keine allgemeine Weisheit, sondern eine Beobachtung an diesem Datentyp. Hochschularbeiten sind zwischen etwa 4.000 und über 80.000 Wörtern lang – eine Spannweite von mehr als dem Zwanzigfachen. Auf einem Bestand von Aufsätzen mit 300 bis 800 Wörtern, wie er in Vergleichsstudien üblich ist, kann sich der Effekt kaum entfalten; hier entfaltet er sich voll.

Gemessen an einer Stichprobe von 80 Arbeiten: Bei englischen Arbeiten hatten **5 von 16** untersuchten Metriken einen Betrag der Korrelation über 0,5 mit der Wortzahl, bei deutschen **7 von 16**. In der Vergleichsstudie mit kurzen Aufsätzen waren es etwa 4. (Die Stichprobe war klein und enthielt 4 unbrauchbare Extraktionen; die Größenordnung ist belastbarer als die genauen Zahlen.)

Verschärfend kommt hinzu: Der Umfang hängt an der **Abschlussart**. Bachelorarbeiten sind kürzer als Masterarbeiten. Ein Vergleich beider Gruppen auf einer längenabhängigen Metrik ist damit fast garantiert ein Vergleich ihrer Länge – und ein sehr überzeugend aussehender.

## Welche Metriken betroffen sind

**Stark betroffen** – nicht ohne Kontrolle der Länge verwenden:

- [ttr](metric:ttr) – bei diesem Umfangsbereich eher ein Längenmaß als ein Wortschatzmaß
- [hapax_token_ratio](metric:hapax_token_ratio)
- alle reinen Zählungen ([word_count](metric:word_count), [char_count_alpha](metric:char_count_alpha), [sentence_count](metric:sentence_count), [n_pages](metric:n_pages), [text_chars](metric:text_chars)) – sie *sind* Längenmaße, was in Ordnung ist, solange man sie so behandelt

**Teilweise betroffen:**

- [root_ttr](metric:root_ttr) – die Wurzelkorrektur nimmt den größten Teil heraus, nicht alles
- [hapax_type_ratio](metric:hapax_type_ratio) – schwächer als die Schwestermetrik, aber nicht frei davon

**Weitgehend stabil** (Betrag der Korrelation mit der Wortzahl unter 0,3 in beiden Sprachen):

- [avg_word_len](metric:avg_word_len)
- [std_sentence_len](metric:std_sentence_len)
- [yules_k](metric:yules_k)
- [flesch_reading_ease](metric:flesch_reading_ease)

Diese vier sind die einzigen, die man zwischen Arbeiten sehr unterschiedlichen Umfangs unbesehen vergleichen darf. Im Bericht sagt deshalb eine Abweichung von der Referenz bei diesen vier am meisten ([Ausreißererkennung](concept:outlier_detection)).

## Was man dagegen tun kann

1. **Auf eine der vier stabilen Metriken ausweichen**, wenn die Frage es zulässt. Das ist der einfachste und ehrlichste Weg.
2. **Nach Länge gruppieren** und innerhalb der Gruppen vergleichen – etwa getrennt nach [thesis_type](metric:thesis_type), was Umfangsklassen grob abbildet.
3. **Die Länge als Kontrollgröße mitführen.** Bevor ein Zusammenhang zwischen zwei Metriken oder eine Entwicklung über die Jahre berichtet wird: gegen [word_count](metric:word_count) prüfen. Bleibt der Befund bei kontrollierter Länge erhalten, ist er belastbar; verschwindet er, war es die Länge.
4. **Es dazusagen.** Wird eine längenabhängige Metrik berichtet, gehört ihre Längenabhängigkeit in dieselbe Aussage – nicht in eine Fußnote.

Und der zeitliche Sonderfall: Wenn der Umfang von Hochschularbeiten über die Jahre zu- oder abnimmt, wandert **jede** längenabhängige Metrik über die Jahre mit. Das sieht wie eine Veränderung des Schreibens aus und ist eine Veränderung der Vorgaben.
