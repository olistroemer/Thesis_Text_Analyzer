# Thesis Text Analyzer (`tta`)

<!-- Der einleitende Absatz und die Abschnitte "Hintergrund" und "Datenschutz"
     stehen in einfacherer Sprache auch auf der Startseite der Hilfe:
     tta/core/help/guide/de/cover.md (Deutsch) und .../en/cover.md (Englisch).
     Bei Änderungen beide anpassen; tests/core/test_help_corpus.py prüft, dass
     die Abkürzungen und Jahreszahlen übereinstimmen (#92). -->

Eine portable Desktop-Anwendung, die Abschlussarbeiten (PDF) lokal und offline analysiert: Sie berechnet Textmerkmale wie Länge, Satz- und Wortstatistiken, Lesbarkeit und Wortschatz, zeigt sie in einer Tabelle und einem Bericht an und erzeugt auf Wunsch einen anonymen Export für das Forschungsteam. Die Anwendung gibt es als grafische Oberfläche (`tta-gui`) für Lehrende und als Kommandozeile (`tta`) für das Forschungsteam.

<!-- Das Bild ist kein Teil des Repositorys: Es ist ein Asset jedes Releases,
     das CI erzeugt (ADR-0014, SDD §5.6.5). releases/latest zeigt nur auf
     ein veröffentlichtes Release (kein Entwurf, keine Vorabversion); vor dem
     ersten veröffentlichten Release ist das Bild daher nicht zu sehen. -->
![Hauptfenster nach einem Analyselauf: Tabelle mit einer Zeile je Arbeit und Kennzahlen wie Seiten, Jahr, Sprache, Wortzahl und Lesbarkeit; eine Arbeit ist ausgeschlossen, eine als unlesbar markiert, eine fehlerhaft](https://github.com/olistroemer/Thesis_Text_Analyzer/releases/latest/download/app-hauptfenster-basis.png)

*Das Hauptfenster nach einem Analyselauf, mit synthetischen Beispieldaten. Das Bild stammt aus dem neuesten [Release](https://github.com/olistroemer/Thesis_Text_Analyzer/releases/latest) und zeigt dessen Stand.*

## Überblick

- **Analyse:** 13 Module mit 34 Kennzahlen ([ADR-0011](docs/adr/0011-mvp-module-catalogue.md)), darunter Länge, Satz- und Wortstatistiken, Lesbarkeit, Wortschatz und Abbildungen; Art der Arbeit und Erscheinungsjahr werden vom Titelblatt gelesen. Die Textkennzahlen beziehen sich auf den Fließtext ohne Quellcode und Formeln ([ADR-0024](docs/adr/0024-two-text-views.md)).
- **Bericht:** eine eigenständige HTML-Datei mit interaktiven Diagrammen, die auch offline funktioniert. Sie vergleicht die eigenen Arbeiten mit Referenzwerten aus Bachelor- und Masterarbeiten der HU Berlin und der ETH Zürich, die als zusammengefasste Kennwerte in der Anwendung mitgeliefert werden ([ADR-0016](docs/adr/0016-report-view.md), [ADR-0025](docs/adr/0025-reference-aggregates.md)).
- **Hilfe:** in der Anwendung, mit einer Startseite zum Projekt, einer Seite je Kennzahl und der Datenschutzerklärung; auf der Kommandozeile `tta help`.
- **Export:** eine anonyme SQLite-Datei für das Forschungsteam ([ADR-0007](docs/adr/0007-export-format.md)).

## Herunterladen

Die Anwendung steht unter [Releases](https://github.com/olistroemer/Thesis_Text_Analyzer/releases) für Windows, macOS (Apple Silicon und Intel) und Linux bereit, jeweils als eine einzelne Datei `tta-gui-<Plattform>`, die ohne Installation startet. Die Dateien sind nicht signiert: Beim ersten Start unter Windows *Weitere Informationen → Trotzdem ausführen* wählen, unter macOS die Datei mit Rechtsklick → *Öffnen* starten. Beim ersten Start legt die Anwendung den Projektordner `TTA-Theses` im Benutzerverzeichnis an; außerhalb ihrer Projektordner schreibt sie nichts ([ADR-0014](docs/adr/0014-distribution.md)).

## Kommandozeile

Die Kommandozeile `tta` wird aus dem Quellcode verwendet (Python 3.11 oder neuer); `pip install -e .` ist eine vollständige Installation, PyMuPDF eingeschlossen:

```bash
pip install -e .
python -m nltk.downloader punkt_tab cmudict
tta -C <Projektordner> run <PDF-Dateien oder Ordner>
tta -C <Projektordner> report
tta --help
```

Die Kommandozeile kann alles, was die Oberfläche kann, und bietet zusätzlich Optionen für das Forschungsteam ([ADR-0003](docs/adr/0003-cli-first-class.md)). Die erste ist `tta run --cover-rules <Datei>`: Sie wendet repository-spezifische Titelblattregeln an, etwa [`research/cover_rules/eth_research_collection.toml`](research/cover_rules/) für die ETH Research Collection ([ADR-0023](docs/adr/0023-researcher-cover-rulesets.md), [`docs/titlepage-rules.md`](docs/titlepage-rules.md)). Die Anwendung selbst liefert keine solchen Regeln aus.

## Hintergrund

Das vorliegende Projekt ist im Kontext der Forschungsgruppe KIWIT (Funktionen und Folgen Künstlicher Intelligenz in der Wissenschafts- und Hochschulorganisation) entstanden, die seit April 2025 vom BMFTR gefördert wird. KIWIT untersucht in einem interdisziplinären Verbund aus Universität Oldenburg, Universität Bielefeld und der Northern Business School Hamburg, welche Funktionen und Folgen KI in Wissenschaft und Hochschulorganisationen entfaltet.

Das Erhebungsprojekt ist dem Forschungsprofil A (Makroebene) zugeordnet und greift eine der zentralen empirischen Fragen von KIWIT auf: Wie verändert der Einsatz generativer KI die wissenschaftliche Schreibpraxis? Abschlussarbeiten stellen dabei ein besonders geeignetes Analyseobjekt dar, da sie in hoher Zahl vorliegen, einem standardisierten Format folgen und ihren Entstehungszeitraum dokumentieren. Über die Analyse von Textmerkmalen — darunter insbesondere Länge und strukturelle Kennwerte — soll systematisch untersucht werden, ob und in welchem Ausmaß der Einsatz KI-gestützter Schreibwerkzeuge seit deren breiter Verfügbarkeit ab Ende 2022 messbare Spuren in akademischen Qualifikationsarbeiten hinterlassen hat.

## Datenschutz

Die Anwendung arbeitet vollständig auf dem eigenen Rechner und baut keine Netzverbindungen auf. Daten verlassen den Rechner nur, wenn ein Export erstellt und selbst weitergegeben wird; dieser enthält keine Personennamen, Dateinamen oder Texte aus den Arbeiten. Die vollständige Datenschutzerklärung steht in der Anwendung unter *Hilfe → Datenschutzerklärung* und auf der Kommandozeile unter `tta privacy report`.

## Dokumentation

Maßgeblich für Anforderungen, Architektur und Verhalten ist das **Software Design Document** ([`docs/SDD.md`](docs/SDD.md)); der Code folgt dem SDD. Einzelne Entwurfsentscheidungen sind als **Architecture Decision Records** in [`docs/adr/`](docs/adr/) begründet. SDD und ADRs sind auf Englisch verfasst.

| ADR | Thema |
|---|---|
| [0001](docs/adr/0001-ui-toolkit.md) | Oberfläche: tkinter + tksheet |
| [0002](docs/adr/0002-ui-core-boundary.md) | Trennung von Oberfläche und Kern (hexagonale Architektur) |
| [0003](docs/adr/0003-cli-first-class.md) | Kommandozeile als gleichwertiger Zugang; ihr Funktionsumfang umfasst den der Oberfläche |
| [0004](docs/adr/0004-module-contract.md) | Vertrag der Analysemodule |
| [0005](docs/adr/0005-producer-swap-deferred.md) | Austausch von Produzenten zurückgestellt |
| [0006](docs/adr/0006-schema.md) | Datenbankschema |
| [0007](docs/adr/0007-export-format.md) | Exportformat |
| [0008](docs/adr/0008-superseded.md) | (ersetzt) |
| [0009](docs/adr/0009-privacy-as-code.md) | Datenschutz-Metadaten als Code, generierte Datenschutzerklärung |
| [0010](docs/adr/0010-sdd-authoring.md) | Erstellung des SDD |
| [0011](docs/adr/0011-mvp-module-catalogue.md) | Modulkatalog: 13 Module, 34 Metriken |
| [0012](docs/adr/0012-help-content.md) | Hilfetexte |
| [0013](docs/adr/0013-runner-orchestration.md) | Ablaufsteuerung der Analysen |
| [0014](docs/adr/0014-distribution.md) | Auslieferung als einzelne ausführbare Datei; Build und Release |
| [0015](docs/adr/0015-performance-budget.md) | Leistungsbudget |
| [0016](docs/adr/0016-report-view.md) | Bericht als eigenständige, interaktive HTML-Datei |
| [0017](docs/adr/0017-license.md) | Lizenz |
| [0018](docs/adr/0018-ascii-source.md) | Python-Quelltext nur in ASCII |
| [0019](docs/adr/0019-thesis-type-by-detection.md) | Art der Arbeit wird erkannt, nicht abgefragt |
| [0020](docs/adr/0020-i18n-mechanism.md) | Übersetzung (gettext) |
| [0021](docs/adr/0021-image-counting.md) | Abbildungen zählen, ohne sie zu dekodieren |
| [0022](docs/adr/0022-publication-date-rules.md) | Erscheinungsjahr vom Titelblatt nach festen Regeln |
| [0023](docs/adr/0023-researcher-cover-rulesets.md) | Repository-spezifische Titelblattregeln nur für das Forschungsteam |
| [0024](docs/adr/0024-two-text-views.md) | Zwei Textfassungen: Rohtext zur Erkennung, Fließtext für die Kennzahlen |
| [0025](docs/adr/0025-reference-aggregates.md) | Mitgelieferte Referenzwerte für den Bericht |

Weitere Dokumente: [`docs/user-stories.md`](docs/user-stories.md) (User Stories), [`docs/dependencies.md`](docs/dependencies.md) (verwendete Bibliotheken und ihre Lizenzen), [`docs/model-limitations.md`](docs/model-limitations.md) (Grenzen der verwendeten Modelle und Formeln), [`docs/titlepage-rules.md`](docs/titlepage-rules.md) (Regeln für Erscheinungsjahr und Art der Arbeit).

## Entwicklung

Entwickelt wird unter Linux und nativ unter Windows; die Einrichtung beschreibt [SDD §5.6.3](docs/SDD.md#563-development-environment-linux-and-native-windows). Kurzfassung:

```bash
conda create -n pds python=3.12
conda activate pds
pip install -e ".[dev,build]" "pytest-cov>=5"
python -m nltk.downloader punkt_tab cmudict
python -m pytest -q
```

Änderungen am Verhalten werden zuerst im SDD bzw. in einem ADR beschrieben und danach umgesetzt. Die CI ([SDD §5.6.4](docs/SDD.md#564-ci-pipeline)) testet jeden Push unter Linux und Windows und baut die ausführbaren Dateien für alle vier Plattformen; das Bauen beschreibt [ADR-0014](docs/adr/0014-distribution.md).

Die Screenshots für die Projektdokumentation erzeugt `python tools/screenshots.py --out <Ordner>` (unter Windows, aus synthetischen Beispieldaten; einzelne Bilder mit `--only <Name> ...`, Liste mit `--list`). Details: [SDD §5.6.5](docs/SDD.md#565-documentation-screenshots) und der Docstring des Skripts.

## Release (für Maintainer)

Ein Release entsteht aus einem Tag `v<Version>` ([ADR-0014](docs/adr/0014-distribution.md)):

1. Version in `pyproject.toml` und `tta/__init__.py` setzen (beide gleich; die CI bricht ab, wenn der Tag nicht `v` + Version lautet), auf `main` pushen und die CI abwarten.
2. Optional als Probelauf: *Actions → CI → Run workflow* auf `main`. Er lädt die Binärdateien und den README-Screenshot (Artefakt `screenshot`) hoch, ohne ein Release anzulegen.
3. `git tag v1.0.0 && git push origin v1.0.0`. Die CI baut alle vier Plattformen, der Windows-Build erzeugt `app-hauptfenster-basis.png`, und der Job `release` legt einen **Entwurf** mit den vier `tta-gui-*`-Dateien, den vier `THIRD_PARTY_LICENSES-*.txt` und dem Screenshot an.
4. Den Entwurf prüfen. Fehlt der Screenshot (die Aufnahme auf dem CI-Rechner ist nicht blockierend; der Job meldet dann eine Warnung), ihn lokal unter Windows erzeugen und anhängen: `python tools/screenshots.py --out shots --only app-hauptfenster-basis` und `gh release upload v1.0.0 shots/app-hauptfenster-basis.png`.
5. Veröffentlichen (*Publish release* oder `gh release edit v1.0.0 --draft=false`). Erst dann zeigt `releases/latest` – und damit das Bild oben – auf das neue Release.

Schlägt der Tag-Lauf fehl: Entwurf samt Tag löschen (`gh release delete v1.0.0 --cleanup-tag --yes`; gibt es keinen Entwurf, `git push --delete origin v1.0.0`), den lokalen Tag löschen (`git tag -d v1.0.0`), auf `main` korrigieren und neu taggen.

## Lizenz

GPL-3.0-or-later, siehe [`LICENSE`](LICENSE) und [ADR-0017](docs/adr/0017-license.md).
