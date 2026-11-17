---
slug: mod_readability
title: Lesbarkeit berechnen
kind: module
consumes: [prose_text, language]
produces_artefacts: []
produces_metrics: [flesch_reading_ease]
applicability: Läuft nur für die erkannten Sprachen `de` und `en`. Für jede andere Sprache lautet das Ergebnis „nicht anwendbar" – es gibt keine passende Formel.
references: [flesch1948, amstad1978, textstat, pyphen, cmudict, bailin2001]
see_also: [metric:flesch_reading_ease, module:mod_classify_language, concept:metric_redundancy]
---

# Lesbarkeit berechnen

Dieses Modul berechnet den **Lesbarkeitsindex** nach Flesch – für englische Arbeiten in Rudolf Fleschs ursprünglicher Fassung [@flesch1948], für deutsche in Toni Amstads deutscher Anpassung [@amstad1978]. Gerechnet wird mit der Bibliothek `textstat` [@textstat].

Beide Formeln bestehen aus genau zwei Größen: der **mittleren Satzlänge** in Wörtern und der **mittleren Silbenzahl** je Wort. Kürzere Sätze und kürzere Wörter ergeben einen höheren Wert. Mehr steckt nicht darin – insbesondere nichts über Aufbau, Fachbegriffe, Kohärenz oder Verständlichkeit im eigentlichen Sinn.

## Ergebnis

Die einzelne Metrik [flesch_reading_ease](metric:flesch_reading_ease). Höhere Werte heißen „leichter". Für andere Sprachen als Deutsch und Englisch entfällt der Lauf; es wird kein Ersatzwert erfunden.

## Die wichtigste Einschränkung: eine andere Zerlegung

`textstat` benutzt **nicht** die Zerlegung von [mod_tokenize](module:mod_tokenize). Es bestimmt Sätze mit einem eigenen, einfachen Suchmuster, verwirft dabei Sätze von zwei Wörtern oder kürzer, und zählt Wörter nach Leerzeichen statt nach Buchstaben. Auf demselben Absatz gemessen ergibt das eine mittlere Satzlänge von 5,71 gegenüber 4,38 aus der Zerlegung – rund 30 % Abweichung.

Praktische Folge, und die häufigste Quelle einer falschen Schlussfolgerung: **[avg_sentence_len](metric:avg_sentence_len) in der Tabelle ist nicht die Satzlänge, die in diesen Wert eingegangen ist.** Eine Bewegung von `flesch_reading_ease` darf nicht mit der angezeigten mittleren Satzlänge erklärt werden, und die beiden dürfen nicht als unabhängige Größen gegeneinander gerechnet werden.

## Silbenzählung: geschätzt, nicht gezählt

Für **Englisch** werden die Silben im CMU-Aussprachewörterbuch nachgeschlagen [@cmudict], das mit dem Programm ausgeliefert wird; nur für unbekannte Wörter – Fachjargon, Eigennamen, Neuschöpfungen – greift eine Trennmuster-Heuristik [@pyphen].

Für **Deutsch** gibt es kein Aussprachewörterbuch; gezählt werden **Trennstellen**, und das ist nicht dasselbe wie Silben. Der Fehler ist einseitig und trifft ausgerechnet die häufigsten Wörter dieses Korpus: An der Nahtstelle von Komposita entsteht ein einbuchstabiges Bruchstück, das als Silbe mitzählt. „Bachelorarbeit" wird mit 6 statt 5 Silben, „Masterarbeit" mit 5 statt 4 gezählt – ebenso „Abschlussarbeit", „Diplomarbeit", „Projektarbeit", „Seminararbeit". Wörter dieser Art stehen auf dem Titelblatt, in der Eigenständigkeitserklärung und in jeder Einleitung.

Weil der Fehler nur in eine Richtung geht, hebt er sich über ein Dokument **nicht auf**: Deutsche Arbeiten werden systematisch als schwerer eingestuft, als sie sind, und zwar um so mehr, je nominaler und komposita-reicher sie formuliert sind. Das ist ein Registerunterschied, kein Verständlichkeitsunterschied.

## Die Formel wurde nie für Hochschularbeiten geprüft

- Fleschs Skala von 0 bis 100 wurde an amerikanischen Schulbüchern und Zeitschriftentexten kalibriert. Wissenschaftliche Prosa liegt **unterhalb** dieser Skala; negative Werte sind normal, und die veröffentlichten Bezeichnungen („schwer", „Hochschulniveau") reichen dorthin nicht.
- Amstad hat Fleschs Konstanten in den 1970er Jahren an schweizerischem Zeitungsmaterial neu geschätzt. Eine Deutungsgrundlage für deutsche Wissenschaftssprache existiert in der Literatur nicht.
- Wort- und Satzlänge sind **Stellvertreter**, keine Messung. Bailin und Grafstein zeigen, dass die sprachlichen Annahmen dahinter allgemein nicht tragen [@bailin2001]. Eine Arbeit kann ihre Sätze kürzen, jeden undurchdringlichen Fachbegriff behalten und ihren Wert „verbessern".
- Der Wert ist als **Rangordnung innerhalb eines Korpus** brauchbar. Der absolute Betrag ist es nicht, und Verhältnisse zweier Werte sind bedeutungslos.

Hinzu kommt, dass die Formel über den gesamten extrahierten Text läuft – Literaturverzeichnis, Tabelleninhalte und Kopfzeilen eingeschlossen, mit vollem Gewicht. Nur Code und Formeln sind vorher entfernt (`prose_text`, siehe [mod_extract_pymupdf](module:mod_extract_pymupdf)).

## Kein Netzzugriff

`textstat` versucht bei fehlendem Silbenwörterbuch von sich aus, es aus dem Internet nachzuladen. Das Modul unterbindet das für die Dauer der Berechnung: Das Programm baut keine Netzverbindungen auf. Deutsch rechnet auch ohne dieses Wörterbuch; Englisch nicht und sagt es dann als klar benannten Fehler, statt still einen anderen Wert zu liefern. Ausgelieferte Programmversionen bringen das Wörterbuch mit.
