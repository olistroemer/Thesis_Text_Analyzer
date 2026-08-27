---
slug: language_confidence
title: Sicherheit der Spracherkennung
kind: metric
produced_by: mod_classify_language
applicability: Immer zusammen mit der erkannten Sprache vorhanden.
references: [langdetect]
see_also: [module:mod_classify_language, metric:language_code]
---

# Sicherheit der Spracherkennung (`language_confidence`)

Ein Wert zwischen 0 und 1, der angibt, wie einig sich die Spracherkennung bei [language_code](metric:language_code) war.

## Das ist keine Wahrscheinlichkeit

Der Wert entsteht als **Mittel aus sieben unabhängigen Durchläufen** der Erkennung. Sind sich alle sieben einig, liegt er knapp unter 1,0; widersprechen sie sich, kann er nur Vielfache von einem Siebtel treffen – 0,143, 0,286, 0,429, 0,571, 0,714, 0,857.

Er ist also praktisch eine **siebenstufige Ordnungsskala** („wie viele von sieben Durchläufen waren einer Meinung"), keine kalibrierte Wahrscheinlichkeit. Daraus folgt:

- Nicht als Wahrscheinlichkeit weiterrechnen, nicht mitteln, nicht bei 0,95 abschneiden.
- Ungefähr 1,0 heißt „einstimmig", jeder kleinere Wert heißt „die Erkennung war unsicher". Feiner ist der Wert nicht zu lesen.
- Der Wert 0,8571 bedeutet: sechs von sieben Durchläufen.

Hinzu kommt: Der Zufallsgenerator ist auf einen festen Startwert gesetzt, damit dieselbe Datei stets dasselbe Ergebnis liefert. Ein anderer Startwert hätte auf demselben Text auch einen anderen Sicherheitswert ergeben – gemessen wurden auf einem zweisprachigen Abstract Werte zwischen 0,571 und 1,000 bei **gleichbleibender Sprachangabe**. Der Wert ist damit wiederholbar, aber nicht stabil im tieferen Sinn.

## Was er nicht leistet

Er ist **kein Warnsignal für die häufigste Fehlklassifikation**. Bei einer deutschen Arbeit mit vorangestelltem englischem Abstract ist die Erkennung oft sehr einig – und einig falsch. Ein hoher Wert schließt einen Fehler also nicht aus; nur ein niedriger Wert schließt Verlässlichkeit aus.
