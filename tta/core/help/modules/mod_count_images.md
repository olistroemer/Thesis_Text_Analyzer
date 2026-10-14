---
slug: mod_count_images
title: Abbildungen zählen
kind: module
consumes: []
produces_artefacts: []
produces_metrics: [n_images]
applicability: Läuft für jede Datei mit der Endung `.pdf`; bei jeder anderen Endung lautet das Ergebnis „nicht anwendbar" („not a PDF").
references: [pypdf]
see_also: [metric:n_images, metric:file_size_bytes]
---

# Abbildungen zählen

Dieses Modul liest die PDF-Datei direkt – nicht den extrahierten Text – und zählt die darin **eingebetteten Bilddaten**. Es soll ein grobes Maß für die Bildlastigkeit einer Arbeit liefern. Verwendet wird `pypdf` [@pypdf].

## Verfahren

Für jede Seite werden die Bilder gezählt, die ihr zur Verfügung stehen, und die Zahlen addiert: eingebettete Bildobjekte – auch solche, die in eingebetteten Teil-Grafiken stecken – und direkt in den Seiteninhalt geschriebene Bilder. Ein Bild, das auf mehreren Seiten steht, zählt auf jeder dieser Seiten einmal; mehrfach auf derselben Seite zählt es einmal. Gezählt wird allein anhand des Aufbaus der PDF-Datei: Kein Bild wird dabei geöffnet oder entpackt, deshalb ist das Zählen auch bei gescannten Arbeiten schnell. Es findet keine Auswertung statt: Größe, Position, Inhalt und Rolle eines Bildes werden nicht betrachtet.

## Ergebnis

Die einzelne Metrik [n_images](metric:n_images).

## Warum die Zahl nicht „Anzahl der Abbildungen" heißt

Das Modul ist bewusst ein **Vorläufer** für eine spätere, richtige Abbildungsanalyse. Gezählt werden Bilddaten, nicht Abbildungen, und beide fallen auseinander:

- **Vektorgrafiken werden nicht gezählt.** Ein mit LaTeX-Werkzeugen gesetztes Diagramm besteht aus Zeichenbefehlen, nicht aus Bilddaten. Eine Arbeit mit 30 solchen Diagrammen kann hier bei 0 stehen. Da diese Arbeitsweise mit dem verwendeten Schreibprogramm zusammenhängt, korreliert der Fehler mit [producer_category](metric:producer_category).
- **Ein Bild kann mehrfach zählen.** Große Rasterbilder werden von manchen Werkzeugen in Kacheln zerlegt; jede Kachel zählt einzeln.
- **Nicht jedes Bild ist eine Abbildung.** Hochschullogos auf dem Titelblatt, Zierlinien und Kopfzeilengrafiken zählen mit – teils auf jeder Seite.
- **Eine gescannte Arbeit besteht aus Bildern.** Ein Scan ohne Texterkennung ergibt ein Bild je Seite und gleichzeitig einen leeren oder unbrauchbaren Text.

Die Zahl ist damit als **Rangordnung innerhalb einer technisch ähnlichen Gruppe** brauchbar und als absolute Aussage über die Bebilderung nicht. Wer Bildlastigkeit vergleichen will, sollte zusätzlich [file_size_bytes](metric:file_size_bytes) ansehen und nach [producer_category](metric:producer_category) gruppieren.
