---
slug: text_chars
title: Zeichen (extrahiert)
kind: metric
produced_by: mod_extract_pymupdf
applicability: Immer vorhanden, sobald die Textextraktion gelaufen ist.
see_also: [module:mod_extract_pymupdf, metric:char_count_alpha, metric:word_count]
---

# Zeichen (extrahiert) (`text_chars`)

Die Zahl aller Zeichen im Text, den [mod_extract_pymupdf](module:mod_extract_pymupdf) aus der PDF-Datei gewonnen hat – **einschließlich** Leerzeichen, Zeilenumbrüchen, Ziffern und Satzzeichen.

## Wie man den Wert liest

Als **Kontrollzahl der Extraktion**, nicht als Umfangsmaß der Arbeit. Eine Zahl nahe Null bei einer Datei mit vielen Seiten bedeutet, dass es keine Textebene gibt: die Arbeit ist ein Scan ohne Texterkennung. Ein auffälliges Verhältnis von Zeichen zu [n_pages](metric:n_pages) deutet ebenfalls auf ein Extraktionsproblem hin.

Für Umfangsvergleiche ist [word_count](metric:word_count) die bessere Wahl, und für Zeichenvergleiche [char_count_alpha](metric:char_count_alpha): Diese Zahl hier enthält auch Kopf- und Fußzeilen jeder Seite, Inhaltsverzeichnis, Tabelleninhalte und das gesamte Literaturverzeichnis – und sie zählt Formatierungszeichen mit, deren Menge vom erzeugenden Programm abhängt und nicht von der Arbeit.

Wichtig: Ein hoher Wert sagt **nicht**, dass der Text lesbar ist. Eine Datei mit defekter Glyphenzuordnung liefert vollständige Zeichenmüll-Zeichenketten und damit einen völlig normal aussehenden Wert. Dafür ist [extraction_quality](metric:extraction_quality) zuständig.
