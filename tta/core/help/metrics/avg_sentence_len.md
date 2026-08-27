---
slug: avg_sentence_len
title: Mittlere Satzlänge
kind: metric
produced_by: mod_surface_counts
applicability: Vorhanden, sobald die Zerlegung in Sätze und Wörter gelaufen ist; entfällt bei nicht unterstützter Sprache oder unbrauchbarem Text.
see_also: [module:mod_surface_counts, module:mod_tokenize, metric:sentence_count, metric:flesch_reading_ease, concept:cross_language_comparison]
---

# Mittlere Satzlänge (`avg_sentence_len`)

Wörter je Satz: [word_count](metric:word_count) geteilt durch [sentence_count](metric:sentence_count).

## Wie man den Wert liest

Als Stellvertreter für **syntaktische Komplexität** – mit dem Vorbehalt, dass er die Zuverlässigkeit der Satzerkennung erbt, und die ist bei wissenschaftlicher Prosa begrenzt.

Der Fehler ist **systematisch nach unten** gerichtet, teils um mehr als 30 %: Über-Trennung an Abkürzungen („Abb.", „Tab.", „et al.", „S. 12") und vor allem in Literaturverzeichnissen erzeugt viele Pseudo-Sätze von einem bis vier Wörtern und senkt damit den Mittelwert. Entscheidend ist dabei nicht die Größe des Fehlers, sondern dass er **nicht gleichmäßig** ist: Er wächst mit der Zitierdichte und mit der Zahl der Abbildungsverweise. Eine gründlich referenzierende Arbeit erscheint dadurch kurzatmiger als eine sonst gleiche mit weniger Belegen.

## Die Falle, die am häufigsten zu einem falschen Schluss führt

**Dieser Wert ist nicht die Satzlänge, mit der [flesch_reading_ease](metric:flesch_reading_ease) gerechnet wurde.** Die Lesbarkeitsformel benutzt eine eigene, viel einfachere Satzerkennung und verwirft Sätze von zwei Wörtern oder kürzer. Auf demselben Absatz gemessen: 4,38 hier, 5,71 dort – rund 30 % Unterschied.

Daraus folgt: Eine Bewegung der Lesbarkeitszahl **nicht** mit dieser Spalte erklären, und die beiden nicht als unabhängige Größen gegeneinander rechnen. Es sind zwei verschiedene Messungen desselben Begriffs, und sie widersprechen sich.

## Sprachvergleich

Deutsche Arbeiten liegen deutlich höher (in der Vorarbeit 13,5 gegenüber 9,0 Wörtern). Das ist überwiegend Satzbau der Sprache, nicht Stil der Verfassenden: [Vergleich über Sprachgrenzen](concept:cross_language_comparison).
