---
slug: flesch_reading_ease
title: Lesbarkeit (Flesch)
kind: metric
produced_by: mod_readability
applicability: Vorhanden nur für die erkannten Sprachen `de` und `en`; für jede andere Sprache entfällt die Berechnung.
references: [flesch1948, amstad1978, bailin2001]
see_also: [module:mod_readability, metric:avg_sentence_len, metric:avg_word_len, metric:language_code, concept:metric_redundancy, concept:outlier_detection]
---

# Lesbarkeit (Flesch) (`flesch_reading_ease`)

Der Lesbarkeitsindex nach Flesch – für englische Arbeiten in Rudolf Fleschs ursprünglicher Fassung [@flesch1948], für deutsche in Toni Amstads Anpassung [@amstad1978]. **Höhere Werte heißen „leichter".**

Die Formel besteht aus genau zwei Größen: der mittleren Satzlänge in Wörtern und der mittleren Silbenzahl je Wort. Kürzere Sätze und kürzere Wörter ergeben einen höheren Wert. Mehr steckt nicht darin.

## Wie man den Wert liest: als Rang, nicht als Note

- **Negative Werte sind bei Hochschularbeiten normal.** Fleschs Skala von 0 bis 100 wurde an amerikanischen Schulbüchern und Zeitschriftenprosa kalibriert; wissenschaftliche Texte liegen unterhalb dieser Skala. Die verbreiteten Etiketten („leicht", „schwer", „Hochschulniveau") gelten dort nicht mehr und sind nicht anzuwenden.
- **Verhältnisse und Abstände sind bedeutungslos.** Die Formel ist rechnerisch linear, die Zuordnung zu Verständlichkeit ist es nicht. Ein Abstand von 10 Punkten bei -40 bedeutet nicht dasselbe wie 10 Punkte bei 60.
- **Brauchbar ist die Rangordnung innerhalb eines Korpus** einer Sprache: welche Arbeiten liegen weiter oben, welche weiter unten, wie sieht die Verteilung aus. Als solche gehört diese Metrik zu den vier längenstabilen Größen, auf denen der Bericht Ausreißer bestimmt ([Ausreißererkennung](concept:outlier_detection)).
- **Für Deutsch existiert keine Deutungsgrundlage.** Amstad hat Fleschs Konstanten in den 1970er Jahren an schweizerischem Zeitungsmaterial neu geschätzt. Eine Kalibrierung für deutsche Wissenschaftssprache gibt es in der Literatur nicht.

## Drei Vorbehalte, die vor jeder Aussage stehen sollten

**1. Die Zahl ist ein Stellvertreter, keine Messung.** Wort- und Satzlänge sind mit Schwierigkeit in einigen Textsorten korreliert; sie messen Verständlichkeit nicht. Bailin und Grafstein zeigen, dass die sprachlichen Annahmen dahinter allgemein nicht tragen [@bailin2001]: Satzbau, Kohärenz und Begriffslast sind für die Formel unsichtbar. Eine Arbeit kann ihre Sätze kürzen, jeden undurchdringlichen Fachbegriff behalten und ihren Wert „verbessern".

**2. Sie hängt an einer anderen Satzerkennung als die Tabelle zeigt.** Der Wert wurde **nicht** aus [avg_sentence_len](metric:avg_sentence_len) berechnet, sondern aus einer eigenen, einfacheren Satzerkennung, die Sätze von zwei Wörtern oder kürzer verwirft. Auf demselben Absatz gemessen: 4,38 dort, 5,71 hier. Eine Veränderung der Lesbarkeitszahl darf deshalb **nicht** mit der angezeigten Satzlänge erklärt werden.

**3. Sie sagt fast dasselbe wie [avg_word_len](metric:avg_word_len).** In der Vorarbeit lag der Betrag der Korrelation der beiden bei 0,9 oder darüber – die Wortlänge steckt über die Silbenzahl direkt in der Formel. Beide zu berichten heißt, dasselbe zweimal zu berichten ([Redundanz zwischen Metriken](concept:metric_redundancy)).

## Wann der Wert gar nichts bedeutet

- **Bei falscher Sprache.** Wird eine deutsche Arbeit wegen ihres englischen Abstracts als `en` geführt – der häufigste Fehler dieses Werkzeugs, siehe [language_code](metric:language_code) –, wird sie mit den englischen Konstanten bewertet. Deutsche Wörter haben mehr Silben, das Ergebnis ist eine stark negative, bedeutungslose Zahl, die dennoch als gültiger Wert erscheint und in Diagrammen auftaucht.
- **Bei deutscher Silbenzählung generell etwas zu streng.** Für Deutsch werden Trennstellen statt Silben gezählt, und an Kompositumsnähten entsteht ein einbuchstabiges Bruchstück, das mitzählt: „Bachelorarbeit" wird mit 6 statt 5 Silben gezählt. Der Fehler geht nur in eine Richtung, hebt sich also nicht auf – deutsche Arbeiten werden systematisch als schwerer eingestuft, als sie sind, und zwar um so mehr, je komposita-reicher sie formuliert sind.
- **Bei viel Anhang.** Gerechnet wird über den gesamten extrahierten Text, Literaturverzeichnis und Tabelleninhalte eingeschlossen.

**Kein Nachweis maschinellen Einflusses.** In der Vorarbeit lagen englische Hochschularbeiten mit einem Median von 50,6 näher an der Verteilung maschinell erzeugter Texte einer Vergleichsstudie (Mittel 47,4) als an deren menschlich geschriebenen Texten (Mittel 63,5). Das kann heißen, dass akademische Formalsprache dieselben oberflächlichen Merkmale hat wie maschinell erzeugte Formalsprache. Aus dieser Metrik allein ist es nicht zu entscheiden.
