---
slug: n_pages
title: Seiten
kind: metric
produced_by: mod_extract_pymupdf
applicability: Immer vorhanden, sobald die Textextraktion gelaufen ist.
see_also: [module:mod_extract_pymupdf, metric:page_count_meta, metric:word_count, concept:length_confound]
---

# Seiten (`n_pages`)

Die Zahl der Seiten, die [mod_extract_pymupdf](module:mod_extract_pymupdf) beim Auslesen des Textes durchlaufen hat.

## Wie man den Wert liest

Die Seitenzahl ist das anschaulichste Umfangsmaß und für einen Vergleich das **schwächste**. Sie hängt an Satzspiegel, Schriftgröße, Zeilenabstand, Umfang des Anhangs und der Zahl ganzseitiger Abbildungen – alles Vorgaben des Instituts oder Entscheidungen der Vorlage, nicht Eigenschaften des Textes. Zwei Arbeiten mit gleicher Wortzahl können sich um den Faktor zwei in der Seitenzahl unterscheiden.

Für Umfangsvergleiche ist [word_count](metric:word_count) belastbarer. Die Seitenzahl bleibt nützlich, weil sie die vertraute Größe ist, in der über Hochschularbeiten gesprochen wird, und weil ein Vergleich mit [page_count_meta](metric:page_count_meta) Extraktionsprobleme aufdeckt: Weichen beide Zahlen voneinander ab, hat eine der beiden Bibliotheken die Datei nicht vollständig verstanden.

Da fast alle Verhältniszahlen dieses Werkzeugs mit dem Umfang zusammenhängen, ist der Seitenumfang auch eine **Kontrollgröße**: siehe [Längenabhängigkeit von Metriken](concept:length_confound).
