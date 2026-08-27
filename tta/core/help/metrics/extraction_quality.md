---
slug: extraction_quality
title: Extraktionsqualität
kind: metric
produced_by: mod_check_extraction_quality
applicability: Immer vorhanden, sobald der extrahierte Text vorliegt.
see_also: [module:mod_check_extraction_quality, module:mod_extract_pymupdf, metric:language_code]
---

# Extraktionsqualität (`extraction_quality`)

Das Urteil darüber, ob der aus der PDF-Datei gewonnene Text **brauchbar** ist. Es ist die wichtigste Metrik der Tabelle, denn es entscheidet, ob die übrigen Zahlen derselben Zeile überhaupt etwas bedeuten.

Mögliche Werte:

- `ok` – der Text sieht wie Sprache aus.
- `garbled` – der Text ist Zeichenmüll. Die PDF-Datei enthält keine brauchbare Zuordnung von Glyphen zu Buchstaben; typisch bei älteren, mit LaTeX gesetzten Dateien. **Alle Zahlen dieser Zeile sind bedeutungslos.**
- `sparse` – zu wenig Text, um zu urteilen (weniger als 200 Wortvorkommen). Poster, Auszüge, Scans ohne Texterkennung. Das heißt „nicht beurteilt", nicht „in Ordnung".

Gemessen wird der Anteil sehr häufiger deutscher und englischer Funktionswörter; die Schwelle stammt aus der Vorarbeit dieses Projekts, wo saubere Texte bei 0,149 und darüber und Zeichenmüll bei 0,063 und darunter lagen. Einzelheiten: [mod_check_extraction_quality](module:mod_check_extraction_quality).

## Wie man den Wert benutzt

**Vor jeder inhaltlichen Aussage auf `ok` filtern.** Zeilen mit `garbled` werden vollständig weiter ausgewertet und liefern normal aussehende Werte für Wortschatz, Satzlänge und Lesbarkeit – das ist Absicht, weil das Werkzeug nichts stillschweigend wegwerfen soll, macht die Filterung aber zur Pflicht der Auswertung.

Für zeitliche Vergleiche kommt ein zweiter Grund hinzu: Ältere Dateien sind häufiger betroffen. Ohne Filterung entsteht daraus ein scheinbarer Trend über die Jahre, der nur die Alterung von PDF-Werkzeugen abbildet.

## Grenze der Prüfung

Die Wortliste ist **deutsch und englisch**. Eine einwandfrei extrahierte französische Arbeit wird als `garbled` geführt. Bei einem mehrsprachigen Korpus ist `garbled` daher immer zusammen mit [language_code](metric:language_code) zu lesen.
