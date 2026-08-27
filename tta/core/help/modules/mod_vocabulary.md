---
slug: mod_vocabulary
title: Wortschatzreichtum messen
kind: module
consumes: [tokens]
produces_artefacts: []
produces_metrics: [ttr, root_ttr, hapax_token_ratio, hapax_type_ratio, yules_k]
applicability: Läuft, sobald die Zerlegung (`tokens`) vorliegt. Entfällt, wenn die Zerlegung entfallen ist oder kein einziges Wort enthält.
references: [yule1944, guiraud1954, zipf1949]
see_also: [module:mod_tokenize, concept:length_confound, concept:cross_language_comparison, concept:metric_redundancy]
---

# Wortschatzreichtum messen

Dieses Modul misst, wie **abwechslungsreich** der Wortgebrauch einer Arbeit ist. Alle fünf Metriken beruhen auf derselben Grundlage: den kleingeschriebenen Wörtern aus der Zerlegung, gezählt nach Häufigkeit.

Zwei Begriffe werden dafür gebraucht:

- **Token** – jedes Wortvorkommen. Steht „Untersuchung" 40-mal im Text, sind das 40 Token.
- **Typ** – jedes verschiedene Wort. Dieselben 40 Vorkommen sind ein Typ.
- **Einmalwort** (Hapax) – ein Typ, der genau einmal vorkommt.

## Die fünf Maße

| Metrik | Formel | Idee |
|---|---|---|
| [ttr](metric:ttr) | Typen / Token | einfachste Vielfalt |
| [root_ttr](metric:root_ttr) | Typen / Wurzel(Token) | Guiraud-Index, längenrobuster [@guiraud1954] |
| [hapax_token_ratio](metric:hapax_token_ratio) | Einmalwörter / Token | Anteil einmaliger Wörter am Text |
| [hapax_type_ratio](metric:hapax_type_ratio) | Einmalwörter / Typen | Anteil einmaliger Wörter am Wortschatz |
| [yules_k](metric:yules_k) | Yules Charakteristik K [@yule1944] | längenstabile Wiederholungsneigung |

Beide Hapax-Varianten werden **absichtlich mitgeliefert**, statt eine im Voraus zu wählen: Sie verhalten sich bei wachsender Textlänge unterschiedlich, und welche sich an echten Arbeitskorpora besser bewährt, ist eine Frage, die dieses Projekt beantworten soll, nicht voraussetzen.

Yules K ist das einzige der fünf Maße, das die **gesamte Häufigkeitsverteilung** nutzt und nicht nur Typen und Token zählt. Das ist der Grund für seine Längenstabilität und dafür, dass es die zipfartige Struktur natürlicher Texte [@zipf1949] überhaupt erfassen kann.

## Drei Einschränkungen, die die Zahlen begrenzen

**Längenabhängigkeit.** [ttr](metric:ttr) und [hapax_token_ratio](metric:hapax_token_ratio) sinken systematisch, je länger ein Text ist – das ist ein rechnerischer Zwang, keine Eigenschaft des Schreibens. Bei Hochschularbeiten, deren Umfang um mehr als eine Größenordnung schwankt, misst TTR deshalb **eher die Länge als den Wortschatz**. [root_ttr](metric:root_ttr) und [yules_k](metric:yules_k) sind davon deutlich weniger betroffen. Ausführlich: [Längenabhängigkeit von Metriken](concept:length_confound).

**Keine Grundformen.** Es wird nicht lemmatisiert. „Untersuchung" und „Untersuchungen", „geht" und „ging" sind je zwei Typen. Damit misst der Wortschatzwert zu einem Teil die Formenvielfalt der Sprache mit.

**Sprachen sind nicht vergleichbar.** Deutsche Komposita bleiben ein Token („Datenschutzgrundverordnung"), und die deutsche Flexion erzeugt mehr Formen desselben Wortes. Beides hebt die deutschen Werte auf **allen** fünf Maßen gegenüber englischen an – aus grammatischen Gründen, nicht wegen des Schreibstils. Deutsche und englische Arbeiten dürfen auf diesen Metriken nicht in einen Topf: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).

Hinzu kommt: Am Zeilenende getrennte Wörter überleben die Extraktion als zwei Bruchstücke und erscheinen als zwei zusätzliche Einmalwörter. Wie häufig das ist, hängt am erzeugenden Programm ([producer_category](metric:producer_category)), nicht an der Arbeit.
