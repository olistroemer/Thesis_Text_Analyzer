---
slug: has_outline
title: Lesezeichen
kind: metric
produced_by: mod_extract_pdf_metadata
applicability: Immer vorhanden, sobald die PDF-Metadaten gelesen wurden.
see_also: [module:mod_extract_pdf_metadata, metric:producer_category]
---

# Lesezeichen (`has_outline`)

Gibt an, ob die PDF-Datei einen **Lesezeichenbaum** enthält – jene anklickbare Gliederung, die PDF-Betrachter in einer Seitenleiste anzeigen. Der Wert ist 1 (vorhanden) oder 0 (nicht vorhanden).

## Wie man den Wert liest

Als **technisches Merkmal des Erzeugungswegs**, nicht als Qualitätsmerkmal der Arbeit. Ein Lesezeichenbaum entsteht in der Regel automatisch: LaTeX-Arbeiten mit dem üblichen Paket für Querverweise bringen ihn fast immer mit, ein „Speichern als PDF" aus einer Textverarbeitung je nach Programm und Einstellung. Die Verfassenden treffen diese Entscheidung meist nicht bewusst.

Daraus folgt: Der Wert sagt mehr über [producer_category](metric:producer_category) als über die Gliederungsdisziplin der Arbeit. Als Aussage über Sorgfalt oder Struktur ist er **nicht** zu lesen. Sein Nutzen liegt darin, technisch ähnliche Gruppen von Arbeiten zu bilden – zum Beispiel, um eine zeitliche Auffälligkeit zuerst gegen einen Wandel der Werkzeuge zu prüfen, bevor sie dem Schreiben zugeschrieben wird.
