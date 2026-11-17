---
slug: mod_determine_publication_year
title: Veröffentlichungsjahr bestimmen
kind: module
consumes: [raw_text, pdf_metadata]
produces_artefacts: []
produces_metrics: [publication_year, publication_year_source, publication_date_precision]
applicability: Läuft, sobald extrahierter Text (`raw_text`) und PDF-Metadaten (`pdf_metadata`) vorliegen. Ohne jegliches Datumssignal ist der Lauf trotzdem erfolgreich – mit leerem Jahr und Quelle `none`.
see_also: [metric:publication_year, metric:publication_year_source, metric:publication_date_precision, module:mod_extract_pdf_metadata, module:mod_classify_thesis_type]
---

# Veröffentlichungsjahr bestimmen

Dieses Modul liefert die beste Schätzung des **Veröffentlichungsjahres** einer Arbeit – die X-Achse des primären Forschungsziels (SDD §2.1: Textlänge über das Veröffentlichungsjahr). Es liest das Datum, das die Arbeit selbst auf ihrer **Titelseite** nennt, nach fest definierten, dokumentierten Regeln (ADR-0022, „Datumsregeln v1"). Erst wenn dort kein Datum steht, greift es auf die PDF-Metadaten zurück.

## Wo gesucht wird

- **Titelseite** ist die erste Seite mit mindestens 30 Zeichen (ohne Leerzeichen); leere Vorblätter werden übersprungen.
- Gesucht wird auf der Titelseite und den **drei folgenden Seiten**. In der Auswertung der Referenzsammlung stand das Datum dort in 97,5 % der Arbeiten; die späten Fälle sind Nachdrucke in Schriftenreihen, deren Impressum auf Seite 3–4 steht.
- Die Seiten werden der Reihe nach geprüft; die erste Seite mit einem gültigen Datum entscheidet.

## Welche Datumsformen erkannt werden

Nur Formen, die auf den Titelseiten der Referenzsammlung tatsächlich vorkommen:

- **Tag:** „12. Mai 2014", „March 24, 2005", „Thursday 24th March, 2016", „29.3.1995", „8/15/2008" (US-Schreibweise), „2003-05-26".
- **Monat:** „Mai 2014", „Berlin, im August 2007", „2006-03", „08/2009".
- **Semester:** „Sommersemester 2014", „Wintersemester 1997/98", „SS 2013", „WS 97/98", „FS 2009", „HS 2013", „Spring 2017", „Sommer 2018".
- **Studienjahr:** „2020/2021".
- **Jahr allein**, aber nur an typischen Stellen: allein auf einer Zeile, als Impressum „Berlin, 2009", am Ende einer Titelseitenzeile oder nach „eingereicht im Jahr".

Monatsnamen werden deutsch, englisch und italienisch erkannt, auch abgekürzt („Sept.") und in den typischen Schreib- und Texterkennungsvarianten („Marz", „Maerz").

## Was ausdrücklich nicht zählt

Ein Datum zählt nicht, wenn auf derselben Zeile davor – oder in einer Beschriftungszeile mit Doppelpunkt direkt darüber – einer dieser Hinweise steht:

- **Geburtsdatum** („geboren am", „born on", „Geburtsdatum"),
- **Prüfungs- oder Verteidigungstermin** („Tag der mündlichen Prüfung", „defended on", „akzeptiert"),
- **Copyright** („©", „Copyright"),
- **Abrufdatum** („abgerufen", „accessed", „Stand"),
- **Überarbeitung** („überarbeitet", „revised", „Version with minor changes"),
- **Erstellungsvermerk** („compiled on"),
- **Repository-Angabe** („Publication date:" – das Ablagedatum eines Repositoriums, nicht das Datum der Arbeit).

Außerdem zählen nicht: Jahreszahlen in Klammern oder Literaturangaben, der **Anfang eines Zeitraums** („September 2011 – März 2012" ergibt März 2012), Jahreszahlen im Titel („seit 1945") und Jahre außerhalb von 1900 bis zum Folgejahr. Die Hinweise wirken nur auf ihrer eigenen Zeile – ein Geburtsdatum auf der Zeile darüber verdrängt das Abgabedatum nicht.

Eine Seite mit dem **Metadatenblock eines Repositoriums** (mindestens zwei der Angaben „Publication date:", „Permanent link:", „Rights / license:") liefert kein Datum; sie zählt aber weiterhin als Seite.

**Nach der Titelseite** zählt ein Datum nur mit Abgabe-Hinweis („eingereicht am", „submitted", „Abgabedatum"), in der Form „Ort, (den) Datum" oder allein auf seiner Zeile – Daten im Fließtext („Im Juli 2005 gründete …") zählen nicht.

## Rangfolge auf einer Seite

1. ein Datum mit Abgabe-Hinweis,
2. sonst das genaueste Datum (Tag oder Monat vor Semester, Semester vor Jahr), bei Gleichstand das frühere.

**Semester:** Sommer-, Frühjahrs- und Herbstsemester ergeben das genannte Jahr, ein Wintersemester sein **Endjahr** („WS 2004/05" → 2005). Ein ausdrückliches Datum geht einem Semester vor. **Nachdrucke in Schriftenreihen** erhalten das Jahr der Arbeit („eingereicht im Jahr 2003"), nicht das Erscheinungsjahr der Reihe.

## Signalfusion (nach Priorität)

1. **Datum von der Titelseite** wie oben.
2. **`creation_year`** aus den PDF-Metadaten.
3. **`modification_year`** aus den PDF-Metadaten.

## Ergebnis

Drei Metriken: [publication_year](metric:publication_year) (Zahl, ggf. leer), [publication_year_source](metric:publication_year_source) (welches Signal gewann) und [publication_date_precision](metric:publication_date_precision) (wie genau die Angabe war). Tag und Monat selbst werden **nicht** als Metrik gespeichert und nie exportiert; sie stehen zusammen mit der erkannten Form, der entscheidenden Regel, der Seite und den verworfenen Kandidaten nur in den lokalen Lauf-Notizen.

Für Forschende bietet die Kommandozeile zusätzlich die Option `tta run --cover-rules`, mit der von einem Repositorium vorangestellte Deckblätter übersprungen werden (ADR-0023). Die grafische Oberfläche wendet keine solche Regel an.
