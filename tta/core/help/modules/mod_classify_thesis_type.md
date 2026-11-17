---
slug: mod_classify_thesis_type
title: Abschlussart erkennen
kind: module
consumes: [raw_text]
produces_artefacts: []
produces_metrics: [thesis_type]
applicability: Läuft, sobald der extrahierte Text (`raw_text`) vorliegt. Bei unlesbarem oder sehr kurzem Text wird `unspecified` zurückgegeben – nie „nicht anwendbar".
see_also: [metric:thesis_type, module:mod_classify_language, module:mod_determine_publication_year]
---

# Abschlussart erkennen

Dieses Modul bestimmt die **Abschlussart** einer Arbeit allein aus dem Text ihrer **ersten Seiten**. Es ersetzt den früheren Auswahldialog beim Hinzufügen von Dateien: Die Art wird automatisch erkannt (siehe [ADR-0019]) und kann später über editierbare Metriken korrigiert werden (#10). Die Regeln stammen aus einer Auswertung der Referenzsammlung („Marker v1").

## Verfahren

Untersucht werden die **ersten fünf Seiten** der Arbeit. Bei Nachdrucken in Schriftenreihen steht die Art oft erst im Impressum auf Seite 3–4 („Diese Veröffentlichung geht zurück auf eine Masterarbeit …"). Der Text wird zunächst normalisiert – Kleinschreibung, Auflösung von Umlauten und Akzenten, Vereinheitlichung von Apostrophen, gesperrt gesetzte Wörter („M A S T E R T H E S I S") werden zusammengezogen.

Als Hinweis (Marker) zählen nur **ausgeschriebene** Bezeichnungen der Art oder des Grades, zum Beispiel:

- **Bachelor:** „Bachelorarbeit", „Bachelor's Thesis", „Bachelor-Abschlussarbeit", „… for the degree of Bachelor …".
- **Master:** „Masterarbeit", „Master's Thesis", „M.Sc. Thesis", „… zur Erlangung des Grades Master …".
- **Diplom:** „Diplomarbeit", „Diploma Thesis", ein ausgeschriebener Grad wie „Diplom-Ingenieur" oder „Diplom-Psychologe", „Diplomthema"/„Diplomand(in)", „Hausarbeit zur Diplomprüfung".
- **Magister:** „Magisterarbeit", „Magister/Magistra Artium".
- **MAS (Weiterbildungsmaster):** „Master of Advanced Studies", „MAS-Programm", „Nachdiplomarbeit"/„Nachdiplomstudium".
- **Lizentiat:** „Lizentiatsarbeit".
- **Semester-/Studienarbeit:** „Semesterarbeit", „Semester Thesis/Project", „Studienarbeit", „Focus Work".
- **Dissertation:** „Dissertation zur Erlangung …", „Doctor of Sciences", „Doktorgrad", „Doctoral Thesis", „Doktorarbeit".

Bewusst **nie** als Hinweis gelten Abkürzungen wie „B.Sc.", „M.Sc.", „M.A.", „Dipl.-Ing.", „Dr. sc." oder „PhD", das alleinstehende „Diplom" oder „Dissertation" sowie Wörter wie „Masterstudiengang" oder „Masterplan". Titelseiten nennen im selben Bereich auch Autorinnen, Betreuende und Prüfende mit solchen Titeln – eine Bachelor- oder Masterarbeit würde sonst falsch eingeordnet.

## Entscheidung

- Der **zuerst genannte** gültige Hinweis entscheidet.
- Steht auf derselben Seite wie ein Master-Hinweis „Master of Advanced Studies" oder „MAS-Programm", ist die Arbeit ein **MAS** (Weiterbildung, nicht der konsekutive Master).
- „Nachdiplomarbeit" ist keine Diplomarbeit.
- Nur wenn gar kein solcher Hinweis vorkommt, genügt ein bloßes „Bachelor of Science" oder „Master of Arts" (es kann sonst auch der frühere Abschluss der Autorin sein).
- Fehlt jeder Hinweis – oder ist der Text unbrauchbar –, lautet das Ergebnis `unspecified`.

Das ist eine bewusst **leichtgewichtige Heuristik** (keine KI, kein Modell).

## Ergebnis

Erzeugt die einzelne Metrik [thesis_type](metric:thesis_type). Es gibt bewusst **keine** separate Konfidenz-Metrik; die gefundenen Hinweise, ihre Seite und die entscheidende Regel werden als Beleg in den lokalen Lauf-Notizen abgelegt (verlassen das Gerät nie).

**Jede Arbeit wird so gelesen, wie sie ist.** Die App enthält keine Regeln, die auf den Aufbau eines bestimmten Repositoriums oder einer bestimmten Hochschule zugeschnitten sind – etwa ein beim Herunterladen vorangestelltes Deckblatt oder ein Formular. Liegt ein solches Deckblatt vor der eigentlichen Titelseite, wird es wie jede andere Seite gelesen. Für Forschende bietet die Kommandozeile zusätzlich die Option `tta run --cover-rules`, mit der ein Regelsatz aus einer Datei solche Seiten und Textstellen überspringt oder nicht als Beleg zählt (ADR-0023). Die grafische Oberfläche wendet keine solche Regel an.
