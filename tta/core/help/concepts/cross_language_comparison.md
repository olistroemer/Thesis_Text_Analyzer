---
slug: cross_language_comparison
title: Vergleich über Sprachgrenzen
kind: concept
see_also: [metric:language_code, metric:avg_word_len, metric:ttr, metric:flesch_reading_ease, module:mod_tokenize]
---

# Vergleich über Sprachgrenzen

**Deutsche und englische Arbeiten dürfen auf den Textmetriken dieses Werkzeugs nicht in einen gemeinsamen Topf.** Nicht, weil die Zahlen falsch wären, sondern weil sie in den zwei Sprachen Verschiedenes bedeuten. Ein gemischter Bestand erzeugt Unterschiede, die keiner Eigenschaft des Schreibens entsprechen.

## Wie groß der Unterschied ist

An einer Stichprobe von je 40 deutschen und 40 englischen Hochschularbeiten desselben Instituts, also bei vergleichbarer Fach- und Betreuungskultur:

| Metrik | Deutsch | Englisch |
|---|---|---|
| [avg_word_len](metric:avg_word_len) | 6,15 | 5,07 |
| [avg_sentence_len](metric:avg_sentence_len) | 13,5 | 9,0 |
| [ttr](metric:ttr) | 0,20 | 0,12 |
| [hapax_token_ratio](metric:hapax_token_ratio) | 0,11 | 0,05 |

Für den Einmalwort-Anteil wurde damals eine einzige Kennzahl erhoben, bevor sie in die beiden heutigen Varianten geteilt wurde; die Zeile ist der am Text gemessenen Variante zugeordnet.

Deutsch liegt auf **jeder** dieser Metriken höher, und zwar um 20 bis über 100 Prozent. Das ist um Größenordnungen mehr, als irgendein Effekt, den man in einem Bestand messen möchte, jemals ausmachen wird. Eine Auswertung, die deutsche und englische Arbeiten mischt, misst in erster Linie den Sprachanteil ihres Bestands.

## Woran es liegt

**Komposita.** „Datenschutzgrundverordnung" ist im Deutschen ein Wort, im Englischen wären es drei bis vier. Das hebt die Wortlänge, senkt die Wortzahl bei gleichem Inhalt und erzeugt viele Wörter, die im übrigen Text nie wieder vorkommen – also Einmalwörter. Damit steigen alle Wortschatzmaße.

**Formenreichtum.** Deutsche Flexion erzeugt mehr verschiedene Formen desselben Wortes. Da nicht auf Grundformen zurückgeführt wird, zählt jede Form als eigenes Wort.

**Satzbau.** Nebensatzstruktur und Verbendstellung führen zu längeren Sätzen.

**Und ein Werkzeuggrund obendrauf.** Die Wortzerlegung dieses Programms arbeitet **immer mit englischen Regeln**, auch bei deutschem Text ([mod_tokenize](module:mod_tokenize)). Für Deutsch bedeutet das unter anderem, dass „zum" und „ins" nicht getrennt werden und dass die deutschen Anführungszeichen anders behandelt werden als die englischen. Die deutschen und englischen Werte sind damit nicht nur sprachlich, sondern auch **verfahrenstechnisch** unterschiedlich zustande gekommen.

Bei der Lesbarkeit kommt hinzu, dass für die beiden Sprachen **verschiedene Formeln mit verschiedenen Konstanten** verwendet werden ([flesch_reading_ease](metric:flesch_reading_ease)). Ein deutscher und ein englischer Wert sind dort nicht einmal Ergebnisse derselben Rechnung.

## Was zu tun ist

**Immer nach [language_code](metric:language_code) trennen** und die Auswertung je Sprache durchführen. Auch dann, wenn nur wenige Arbeiten der anderen Sprache im Bestand sind – gerade dann, denn eine kleine Gruppe mit systematisch höheren Werten wirkt wie eine Gruppe von Ausreißern.

**Nicht** versuchen, den Unterschied durch Normierung wegzurechnen. Es gibt für diese Metriken keinen belastbaren Umrechnungsfaktor zwischen Deutsch und Englisch, und ein selbst geschätzter aus dem eigenen Bestand würde genau den Effekt beseitigen, den man vielleicht gerade sucht.

**Und der Verteilung selbst misstrauen.** Bevor man nach Sprache gruppiert, ist zu prüfen, ob die Spalte überhaupt stimmt: Die häufigste Fehlklassifikation dieses Werkzeugs ist eine deutsche Arbeit mit vorangestelltem englischem Abstract, die als `en` geführt wird ([language_code](metric:language_code)). Ein solcher Fall wandert in die englische Gruppe, wird dort mit englischem Satzmodell und englischer Lesbarkeitsformel behandelt – und liegt dann als Ausreißer in der falschen Gruppe.
