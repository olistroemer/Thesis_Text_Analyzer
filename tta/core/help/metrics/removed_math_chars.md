---
slug: removed_math_chars
title: Entfernte Zeichen (Formelschrift)
kind: metric
produced_by: mod_extract_pymupdf
applicability: Immer vorhanden, sobald die Textextraktion gelaufen ist; 0, wenn nichts in einer Formelschrift gesetzt ist.
see_also: [module:mod_extract_pymupdf, metric:removed_monospace_chars, metric:text_chars]
---

# Entfernte Zeichen (Formelschrift) (`removed_math_chars`)

Die Zahl der Zeichen, die [mod_extract_pymupdf](module:mod_extract_pymupdf) aus dem Fließtext entfernt hat, weil sie in einer **Formelschrift** gesetzt sind. Gezählt werden nur sichtbare Zeichen, keine Leerzeichen und Zeilenumbrüche, über die ganze Arbeit.

Als Formelschrift gilt jede Schrift, deren Name „Math" enthält (Cambria Math, die Formelschrift von Word, sowie STIX Two Math, Latin Modern Math und ähnliche), und die Formelschriften von TeX: die Familien CMMI, CMSY, CMEX, die AMS-Schriften MSAM und MSBM, Euler Fraktur, RSFS und stmaryrd. Die Schrift „Symbol" zählt nicht dazu, weil Word darin Aufzählungszeichen setzt.

## Warum es diese Zahl gibt

Aus Formeln bleiben bei der Extraktion nur Bruchstücke übrig – einzelne Buchstaben, Indizes, Operatoren. Für Satzlängen, Wortschatz und Lesbarkeit sind sie Rauschen, das Arbeiten aus Mathematik, Physik und Technik systematisch anders aussehen lässt. Deshalb rechnen diese Metriken auf dem Text **ohne** Formelschrift. Diese Zahl zeigt, wie viel dafür weggenommen wurde.

## Wie man den Wert liest

- **Als Menge, nicht als Anteil.** Für einen Vergleich setzt man den Wert ins Verhältnis zu [text_chars](metric:text_chars).
- **Nicht alle Formelteile.** TeX setzt Ziffern, Klammern und Operatoren oft in der normalen Textschrift; aus `O(g⁴)` bleibt dann `(4)` im Text. Formeln, die in Word ohne Formeleditor mit normalen Zeichen geschrieben sind, und Formeln, die als Bild eingebunden sind, werden nicht erkannt.
- **Auch etwas mehr als Formeln.** Einzelne Satzzeichen oder Schrägstriche, die TeX in einer Formelschrift setzt, verschwinden mit.
- **Wenn die ganze Arbeit in einer Formelschrift steht, wird nichts entfernt.** In seltenen Word-Dokumenten ist der gesamte Fließtext in Cambria Math gesetzt. Ist mehr als 80 % des Textes einer Arbeit in einer Formelschrift gesetzt, gilt das als Schrift des Fließtextes: Der Text bleibt vollständig erhalten und der Wert ist 0. Formeln in einer solchen Arbeit werden dann nicht herausgerechnet.
