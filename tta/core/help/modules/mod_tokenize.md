---
slug: mod_tokenize
title: In Sätze und Wörter zerlegen
kind: module
consumes: [prose_text, language]
produces_artefacts: [tokens]
produces_metrics: []
applicability: Läuft, wenn die erkannte Sprache `de` oder `en` ist und mindestens ein Satz gefunden wird. Sonst lautet das Ergebnis „nicht anwendbar" – und die drei abhängigen Module entfallen mit.
references: [nltk, kiss2006]
see_also: [module:mod_classify_language, module:mod_surface_counts, module:mod_vocabulary, module:mod_redundancy, concept:length_confound]
---

# In Sätze und Wörter zerlegen

Dieses Modul erzeugt **keine einzige Metrik** – und ist trotzdem das einflussreichste der ganzen Kette. Es zerlegt den extrahierten Text ohne Code und Formeln (`prose_text`, siehe [mod_extract_pymupdf](module:mod_extract_pymupdf)) in Sätze und diese in Wörter und legt das Ergebnis als Zwischenergebnis `tokens` ab. Daraus rechnen [mod_surface_counts](module:mod_surface_counts), [mod_vocabulary](module:mod_vocabulary) und [mod_redundancy](module:mod_redundancy) **13 der 34 Metriken**. Jeder Zerlegungsfehler geht unbemerkt in alle 13 ein.

## Verfahren

Verwendet wird NLTK [@nltk] mit dem Verfahren *Punkt* [@kiss2006] für die Satzgrenzen und einem Regelwerk für die Wortgrenzen. Das Punkt-Modell ist **vortrainiert**: Es hat gelernt, welche Abkürzungen keinen Satz beenden – aber gelernt hat es das auf seinem Trainingskorpus, nicht an der vorliegenden Arbeit.

| Modell | Trainiert auf | Umfang |
|---|---|---|
| `english` | Wall Street Journal (Penn Treebank) | rund 469.000 Wortvorkommen |
| `german` | Neue Zürcher Zeitung | rund 847.000 Wortvorkommen |

Die Satzgrenzen einer heutigen deutschen Masterarbeit werden also von Statistiken aus einer **Schweizer Zeitung der 1990er Jahre** bestimmt. Das ist der größte Abstand zwischen Trainings- und Anwendungsdaten in der ganzen Verarbeitungskette. Das deutsche Trainingskorpus schreibt zudem durchgehend „ss" statt „ß" – das Modell hat dieses Zeichen im Training nie gesehen.

Das Modell wird mit dem Programm ausgeliefert; es wird zu keinem Zeitpunkt etwas aus dem Netz geladen.

## Belegte Fehlerbilder

**Zu viele Satzgrenzen bei Abkürzungen.** Genau die Abkürzungen, die in Hochschularbeiten ständig vorkommen, sind in Zeitungstext selten. `Siehe Abb. 3.2 sowie Tab. 4. Die Werte steigen.` sind zwei Sätze, das Modell macht vier daraus. Bemerkenswert ist die Unregelmäßigkeit: „Vgl." und „ff." werden erkannt, „Abb." und „Tab." nicht. Welche Abkürzung durchkommt, ist ein Zufall des Trainingskorpus – der Fehler trifft also eine abbildungsreiche Arbeit stärker als eine andere.

**Literaturverzeichnisse sind der Extremfall.** Autoreninitialen und Jahreszahlen in Klammern sehen genau wie Satzgrenzen aus. Zwei Literaturangaben ergeben neun „Sätze", alle nur ein bis vier Wörter lang. Ein Literaturverzeichnis trägt damit weit überproportional zu [sentence_count](metric:sentence_count) bei, drückt [avg_sentence_len](metric:avg_sentence_len) und treibt [std_sentence_len](metric:std_sentence_len) – **und zwar proportional zur Zahl der Literaturangaben**, also proportional zu einer Eigenschaft, die man vielleicht gerade messen wollte.

**Zu wenige Satzgrenzen bei Überschriften.** Überschriften haben kein Satzzeichen und verschmelzen mit dem folgenden Satz. Jede Überschrift verlängert einen Satz.

**Silbentrennung am Zeilenende bleibt stehen.** Aus einem am Zeilenende getrennten Wort werden zwei Wortteile. Das erhöht [word_count](metric:word_count), senkt [avg_word_len](metric:avg_word_len) und erzeugt Wörter, die es nicht gibt – was alle Wortschatzmetriken verunreinigt. Ob es passiert, hängt am **erzeugenden Programm**, nicht am Schreibstil: ein LaTeX-Dokument mit Blocksatz trennt weit häufiger als ein Word-Dokument. Jede Auffälligkeit einer Wortschatzmetrik ist deshalb gegen [producer_category](metric:producer_category) zu prüfen.

**Die Wortzerlegung ist immer englisch.** Die Sprachangabe erreicht nur die Satzerkennung; die Wörter werden nach englischen Regeln getrennt. Für Deutsch heißt das unter anderem, dass Komposita ein einziges Wort bleiben – sachlich vertretbar, aber es macht deutsche und englische Werte von [avg_word_len](metric:avg_word_len) und den Wortschatzmetriken **strukturell unvergleichbar**. Siehe [Vergleich über Sprachgrenzen](concept:cross_language_comparison).

## Zwei absichtlich laute Fehlschläge

Ein leeres Zwischenergebnis wird **nie** geschrieben. Findet die Zerlegung keinen einzigen Satz, gilt der Lauf als „nicht anwendbar" mit Begründung, und die drei abhängigen Module entfallen ebenfalls – ehrlich und sichtbar. Ein leeres, aber „erfolgreiches" Ergebnis hätte stattdessen 13 Metriken stillschweigend auf Null gesetzt.

Fehlt das mitgelieferte Punkt-Modell, ist das ein **Fehler**, keine Nichtanwendbarkeit: Es ist ein Mangel der Installation, keine Eigenschaft der Arbeit.
