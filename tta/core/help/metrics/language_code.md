---
slug: language_code
title: Sprache
kind: metric
produced_by: mod_classify_language
applicability: Vorhanden, sobald der extrahierte Text mindestens 200 Zeichen umfasst; sonst entfällt die Erkennung.
references: [langdetect]
see_also: [module:mod_classify_language, metric:language_confidence, metric:extraction_quality, concept:cross_language_comparison]
---

# Sprache (`language_code`)

Die erkannte Hauptsprache der Arbeit als Sprachcode, etwa `de` oder `en`, bestimmt von [mod_classify_language](module:mod_classify_language) [@langdetect].

## Warum dieser Wert mehr ist als eine Spalte

Er ist der einzige Wert der Tabelle, der **andere Module steuert**. Er entscheidet, mit welchem Sprachmodell der Text in Sätze zerlegt wird und welche Lesbarkeitsformel angewandt wird. Ist er falsch, sind nicht eine, sondern rund die Hälfte aller Zahlen dieser Zeile falsch – ohne dass es an ihnen zu sehen wäre.

## Die Fehlerquelle, die man kennen muss

Entschieden wird auf den **ersten etwa 10.000 Zeichen**: Titelblatt, Erklärung, Abstract, Beginn des Inhaltsverzeichnisses. Der Fließtext der Arbeit wird nie gelesen.

Deutsche Hochschularbeiten stellen konventionell **beides** voran – einen englischen `Abstract` und eine deutsche `Zusammenfassung`. Steht der englische Teil zuerst oder ist er länger, wird eine deutsche Arbeit als `en` geführt und anschließend mit der englischen Formel bewertet. Das Ergebnis ist eine stark negative, bedeutungslose Lesbarkeitszahl, die dennoch als gültiger Wert gespeichert wird.

**Prüfung:** die Verteilung dieser Spalte über das gesamte Korpus gegen die Erwartung an die Hochschule halten. Ein Anteil von 30 % `en` an einer deutschen Hochschule ist eine Aussage über die Erkennung, nicht über die Studierenden. Weil es an der Hausordnung des Instituts hängt, ob Abstracts zweisprachig vorangestellt werden, ist der Fehler **institutsgebunden** und hebt sich beim Vergleich mehrerer Hochschulen nicht heraus.

## Weitere Grenzen

- Bei [extraction_quality](metric:extraction_quality) ungleich `ok` ist die Sprachangabe wertlos: Auch Zeichenmüll hat eine Zeichenverteilung und wird zuverlässig irgendeiner Sprache zugeordnet.
- Es gibt **eine** Antwort je Dokument. Eine deutsche Arbeit mit englischen Methodenkapiteln wandert Richtung `en`, ohne dass die Mischung sichtbar wird.
- Die Angabe ist grob (`de`, `en`) – österreichisches, schweizerisches und bundesdeutsches Deutsch sind ein Wert.
- Ist die Sprache weder `de` noch `en`, entfallen Zerlegung und Lesbarkeit vollständig, und damit 14 der 31 Metriken.

**Immer nach Sprache getrennt auswerten**, niemals über Sprachen hinweg: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).
