---
slug: removed_monospace_chars
title: Entfernte Zeichen (Festbreitenschrift)
kind: metric
produced_by: mod_extract_pymupdf
applicability: Immer vorhanden, sobald die Textextraktion gelaufen ist; 0, wenn nichts in einer Festbreitenschrift gesetzt ist.
see_also: [module:mod_extract_pymupdf, metric:removed_math_chars, metric:text_chars]
---

# Entfernte Zeichen (Festbreitenschrift) (`removed_monospace_chars`)

Die Zahl der Zeichen, die [mod_extract_pymupdf](module:mod_extract_pymupdf) aus dem Fließtext entfernt hat, weil sie in einer **Festbreitenschrift** gesetzt sind – einer Schrift, in der jedes Zeichen gleich breit ist (Courier, Consolas, LaTeX' `\texttt`). Gezählt werden nur sichtbare Zeichen, keine Leerzeichen und Zeilenumbrüche, über die ganze Arbeit.

## Warum es diese Zahl gibt

Programmcode wird fast immer in einer Festbreitenschrift gesetzt. Für die Textmetriken ist er kein Text des Verfassers: Ein Quelltextlisting hat keine Sätze, dafür sehr viele kurze „Wörter" und Wiederholungen. Deshalb rechnen Satzlängen, Wortschatz, Wiederholungen und Lesbarkeit auf dem Text **ohne** diese Stellen. Diese Zahl zeigt, wie viel dafür weggenommen wurde. Bei Arbeiten aus der Informatik ist sie typischerweise deutlich größer als null, bei geisteswissenschaftlichen Arbeiten meist null.

## Wie man den Wert liest

- **Als Menge, nicht als Anteil.** Eine lange Arbeit hat bei gleichem Stil mehr entfernte Zeichen als eine kurze. Für einen Vergleich setzt man den Wert ins Verhältnis zu [text_chars](metric:text_chars).
- **Nicht nur Code.** Erkannt wird die Schrift, nicht der Inhalt. In LaTeX setzt `\url` Internetadressen und DOIs in eine Festbreitenschrift; im Literaturverzeichnis kommen so auch bei Arbeiten ohne Code einige hundert Zeichen zusammen. Dateinamen und Befehle im Fließtext zählen ebenfalls mit.
- **Nicht aller Code.** Code, der in einer normalen Schrift gesetzt ist (etwa in Word in Arial), wird nicht erkannt und bleibt im Text.
- **Ein sehr hoher Wert ist ein Warnzeichen.** Ist ein großer Teil der Arbeit betroffen – im Extremfall eine Arbeit, die vollständig in Courier gesetzt ist –, hat der Filter Fließtext entfernt. Dann beruhen alle Textmetriken nur auf dem kleinen Rest, oder sie entfallen ganz.

Wenn eine Schrift sowohl Festbreitenschrift als auch Formelschrift ist, zählt das Zeichen hier und nicht bei [removed_math_chars](metric:removed_math_chars).
