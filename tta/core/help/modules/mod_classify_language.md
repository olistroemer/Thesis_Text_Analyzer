---
slug: mod_classify_language
title: Sprache erkennen
kind: module
consumes: [raw_text]
produces_artefacts: [language]
produces_metrics: [language_code, language_confidence]
applicability: Läuft, sobald der extrahierte Text mindestens 200 Zeichen umfasst. Darunter lautet das Ergebnis „nicht anwendbar" („text too short for confident detection").
references: [langdetect, nakatani2010, cavnar1994]
see_also: [metric:language_code, metric:language_confidence, module:mod_tokenize, module:mod_readability]
---

# Sprache erkennen

Dieses Modul bestimmt die **Hauptsprache** der Arbeit. Es ist die folgenreichste Entscheidung der ganzen Auswertung, denn sie ist nicht nur eine Metrik: Sie **steuert zwei weitere Module**. [mod_tokenize](module:mod_tokenize) wählt danach sein Satzmodell, [mod_readability](module:mod_readability) seine Lesbarkeitsformel. Eine falsche Sprache verfälscht damit nicht eine Zahl, sondern einen ganzen Zweig des Ergebnisses.

## Verfahren

Verwendet wird `langdetect` [@langdetect], die Python-Portierung einer Bibliothek von Nakatani Shuyo [@nakatani2010]. Das Verfahren ist ein naiver Bayes-Klassifikator über Zeichen-N-Gramme [@cavnar1994], verglichen mit 55 festen Sprachprofilen, die aus Wikipedia-Text gebildet wurden. Es ist also kein Modell akademischer Sprache, sondern ein Modell der Wikipedia.

Der Zufallsgenerator ist auf einen festen Startwert gesetzt. Gleicher Text ergibt damit immer dasselbe Ergebnis – das ist für Nachvollziehbarkeit notwendig, macht die Antwort aber nicht „richtiger", sondern nur wiederholbar.

## Ergebnis

- [language_code](metric:language_code) – der Sprachcode, etwa `de` oder `en`.
- [language_confidence](metric:language_confidence) – die zugehörige Sicherheit zwischen 0 und 1.
- das Zwischenergebnis `language`, das die beiden folgenden Module lesen.

## Die wichtigste Einschränkung: nur der Anfang wird gelesen

Die Erkennung bekommt den Textanfang, und die Bibliothek kürzt intern noch weiter: Entschieden wird auf den **ersten etwa 10.000 Zeichen**. Das sind Titelblatt, Erklärung, Danksagung, Abstract und der Beginn des Inhaltsverzeichnisses. **Der eigentliche Fließtext der Arbeit wird nie gelesen.**

Daraus folgt die typischste Fehlklassifikation dieses Werkzeugs: Deutsche Hochschularbeiten enthalten konventionell **sowohl einen englischen `Abstract` als auch eine deutsche `Zusammenfassung`**, und zwar genau in diesem Bereich. Steht der englische Teil zuerst oder ist er länger, wird eine deutsche Arbeit als `en` geführt – und anschließend mit englischem Satzmodell zerlegt und mit der englischen Lesbarkeitsformel bewertet. Es gibt im Programm keine Warnung dafür.

**Praktische Absicherung:** Die Verteilung von [language_code](metric:language_code) über das ganze Korpus gegen die Erwartung an die Hochschule prüfen. Ein Anteil von 30 % `en` an einer deutschen Hochschule ist eine Aussage über die Erkennung, nicht über die Studierenden. Weil es an der Hausordnung des Instituts hängt, ob Abstracts zweisprachig vorangestellt werden, ist dieser Fehler **institutsgebunden und nicht zufällig** – er hebt sich in Vergleichen zwischen Hochschulen also nicht heraus.

## Weitere Grenzen

- **Die Erkennung sagt nie „ich weiß es nicht".** Sie kennt 55 Sprachen und gibt stets die wahrscheinlichste davon zurück. Auf Formel- und Zitatfragmenten kommen beliebige Sprachen heraus.
- **Zeichenmüll wird klassifiziert wie Text.** Eine unbrauchbare Extraktion hat ebenfalls eine Zeichenverteilung. Bei [extraction_quality](metric:extraction_quality) ungleich `ok` ist die Sprachangabe wertlos.
- **Keine Mehrsprachigkeit.** Es gibt eine Antwort pro Dokument. Eine deutsche Arbeit mit englischen Methodenkapiteln wandert Richtung `en`, ohne dass die Mischung irgendwo sichtbar würde.
- **200 Zeichen sind eine niedrige Hürde.** Kurze oder verstümmelte Dokumente überschreiten sie und erhalten eine selbstbewusste falsche Antwort.
