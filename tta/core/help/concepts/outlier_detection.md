---
slug: outlier_detection
title: Ausreißererkennung
kind: concept
see_also: [concept:length_confound, metric:avg_word_len, metric:std_sentence_len, metric:yules_k, metric:flesch_reading_ease]
---

# Ausreißererkennung

Ein **Ausreißer** ist in diesem Werkzeug eine Zahl, die im Vergleich zu den übrigen Arbeiten desselben Bestands ungewöhnlich weit außen liegt. Die Tabelle hebt solche Zellen farblich hervor. Der Bericht vergleicht anders: nicht mit dem eigenen Bestand, sondern mit dem Referenzkorpus (siehe unten).

## Das Verfahren

Verwendet wird der **Interquartilsabstand** – dasselbe Verfahren, das den Antennen eines Kastendiagramms zugrunde liegt.

Für eine Metrikspalte:

1. Die Werte aller Arbeiten werden sortiert.
2. Q1 ist der Wert, unter dem ein Viertel der Arbeiten liegt; Q3 der, unter dem drei Viertel liegen. Der Abstand zwischen beiden ist der Interquartilsabstand (IQR) – der Bereich, in dem die **mittlere Hälfte** aller Arbeiten liegt.
3. Die Grenzen liegen bei **Q1 minus 1,5 mal IQR** und **Q3 plus 1,5 mal IQR**.
4. Alles außerhalb dieser Grenzen ist ein Ausreißer.

Der Faktor 1,5 ist Konvention, keine Ableitung. Er stammt aus der Kastendiagramm-Tradition und ist bewusst derselbe, den die üblichen Statistikwerkzeuge voreinstellen – damit ein hier hervorgehobener Wert derselbe ist, der in einem anderswo gezeichneten Kastendiagramm außerhalb der Antennen liegt.

Enthält eine Spalte **weniger als vier** Zahlenwerte, wird nichts hervorgehoben: Quartile über drei Werte sind keine Aussage.

## Wo es sichtbar wird

- **In der Tabelle**: je Metrikspalte gerechnet, über die Arbeiten, die tatsächlich einen Wert haben. Fehlende und fehlerhafte Zellen zählen nicht mit.
- **Im Bericht, Kastendiagramme „Ihre Arbeiten je Jahr"**: dieselben Grenzen; die Antennen reichen bis zum äußersten Wert **innerhalb** der Grenze, weiter außen liegende Werte werden als einzelne Punkte gezeichnet.
- **Im Bericht, Diagramme „… über die Zeit"**: hier ist der Maßstab nicht der eigene Bestand, sondern das **Referenzkorpus** desselben Jahres (bei gewählter Art und Sprache auch desselben Fachs). Hervorgehoben wird eine Arbeit, deren Wert außerhalb des 25.–75. Perzentils der Referenz liegt, stärker, wenn er außerhalb des 5.–95. Perzentils liegt. Diese Arbeiten listet das Diagramm darunter mit einem Verweis auf das PDF auf. Die vier **längenstabilen** Metriken – [avg_word_len](metric:avg_word_len), [std_sentence_len](metric:std_sentence_len), [yules_k](metric:yules_k) und [flesch_reading_ease](metric:flesch_reading_ease) – sind dabei die aussagekräftigsten.

## Was ein Ausreißer nicht ist

**Kein Qualitätsurteil.** Die Hervorhebung sagt „dieser Wert liegt weit außen im Vergleich zu den anderen Arbeiten in diesem Bestand" – nicht „diese Arbeit ist schlecht" und nicht „hier wurde etwas manipuliert".

**Keine Eigenschaft der Arbeit, sondern des Bestands.** Die Grenzen werden aus den vorhandenen Zeilen berechnet. Kommen Arbeiten hinzu oder wird gefiltert, verschieben sich die Grenzen, und dieselbe Arbeit kann aufhören, ein Ausreißer zu sein. Bei kleinen Beständen von etwa zehn Arbeiten sind die Grenzen weitgehend beliebig.

**Auf einer längenabhängigen Metrik nur ein Hinweis auf die Länge.** Ein Ausreißer auf [ttr](metric:ttr) ist meist eine besonders kurze oder besonders lange Arbeit und keine Auffälligkeit des Wortschatzes. Deshalb sind im Bericht die vier längenstabilen Metriken die aussagekräftigsten. Siehe [Längenabhängigkeit von Metriken](concept:length_confound).

**Häufig ein Datenfehler.** Die erste Frage bei einer hervorgehobenen Zelle sollte lauten, ob die Textextraktion dieser Arbeit in Ordnung war: [extraction_quality](metric:extraction_quality) prüfen und ebenso, ob [language_code](metric:language_code) plausibel ist. Zeichenmüll und falsch erkannte Sprachen sind die häufigsten Ursachen extremer Werte.

**Bei vielen Spalten teilweise Zufall.** Das Werkzeug zeigt 34 Metriken. Wird jede Spalte einzeln geprüft, fällt schon aus statistischen Gründen ein Teil der Zellen auf, ohne dass etwas dahintersteht. Eine einzelne hervorgehobene Zelle ist ein Anlass zum Nachsehen, kein Befund.

## Was das Verfahren nicht kann

Es prüft jede Metrik **für sich**. Eine Arbeit, die auf keiner einzelnen Spalte auffällt, deren **Kombination** von Werten aber ungewöhnlich ist – kurze Sätze bei sehr großem Wortschatz etwa –, wird nicht gefunden. Mehrdimensionale Verfahren, die das leisten, sind bewusst nicht Teil dieser Fassung (SDD §12).
