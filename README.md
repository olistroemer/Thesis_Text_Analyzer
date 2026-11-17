# Thesis Text Analyzer (`tta`)

Eine portable Desktop-Anwendung, die Abschlussarbeiten (PDF) lokal und offline analysiert: Sie berechnet Textmerkmale wie Länge, Satz- und Wortstatistiken, Lesbarkeit und Wortschatz, zeigt sie in einer Tabelle und einem Bericht an und erzeugt auf Wunsch einen anonymen Export für das Forschungsteam. Die Anwendung gibt es als grafische Oberfläche (`tta-gui`) für Lehrende und als Kommandozeile (`tta`) für das Forschungsteam.

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
| [0003](docs/adr/0003-cli-first-class.md) | Kommandozeile als gleichwertiger Zugang |
| [0004](docs/adr/0004-module-contract.md) | Vertrag der Analysemodule |
| [0005](docs/adr/0005-producer-swap-deferred.md) | Austausch von Produzenten zurückgestellt |
| [0006](docs/adr/0006-schema.md) | Datenbankschema |
| [0007](docs/adr/0007-export-format.md) | Exportformat |
| [0008](docs/adr/0008-superseded.md) | (ersetzt) |
| [0009](docs/adr/0009-privacy-as-code.md) | Datenschutz-Metadaten als Code, generierte Datenschutzerklärung |
| [0010](docs/adr/0010-sdd-authoring.md) | Erstellung des SDD |
| [0011](docs/adr/0011-mvp-module-catalogue.md) | Modulkatalog: 13 Module, 31 Metriken |
| [0012](docs/adr/0012-help-content.md) | Hilfetexte |
| [0013](docs/adr/0013-runner-orchestration.md) | Ablaufsteuerung der Analysen |
| [0014](docs/adr/0014-distribution.md) | Auslieferung als einzelne ausführbare Datei |
| [0015](docs/adr/0015-performance-budget.md) | Leistungsbudget |
| [0016](docs/adr/0016-report-view.md) | Bericht als eigenständige HTML-Datei |
| [0017](docs/adr/0017-license.md) | Lizenz |
| [0018](docs/adr/0018-ascii-source.md) | Python-Quelltext nur in ASCII |
| [0019](docs/adr/0019-thesis-type-by-detection.md) | Art der Arbeit wird erkannt, nicht abgefragt |
| [0020](docs/adr/0020-i18n-mechanism.md) | Übersetzung (gettext) |

Weitere Dokumente: [`docs/user-stories.md`](docs/user-stories.md) (User Stories), [`docs/dependencies.md`](docs/dependencies.md) (verwendete Bibliotheken und ihre Lizenzen), [`docs/model-limitations.md`](docs/model-limitations.md) (Grenzen der verwendeten Modelle und Formeln).

## Entwicklung

Entwickelt wird unter Linux und nativ unter Windows; die Einrichtung beschreibt [SDD §5.6.3](docs/SDD.md#563-development-environment-linux-and-native-windows). Kurzfassung:

```bash
conda create -n pds python=3.12
conda activate pds
pip install -e ".[dev,build]" "pytest-cov>=5"
python -m nltk.downloader punkt_tab cmudict
python -m pytest -q
```

Änderungen am Verhalten werden zuerst im SDD bzw. in einem ADR beschrieben und danach umgesetzt. Das Bauen der ausführbaren Dateien beschreibt [ADR-0014](docs/adr/0014-distribution.md).

Die Screenshots für die Projektdokumentation erzeugt `python tools/screenshots.py --out <Ordner>` (unter Windows, aus synthetischen Beispieldaten; einzelne Bilder mit `--only <Name> ...`, Liste mit `--list`). Details: [SDD §5.6.5](docs/SDD.md#565-documentation-screenshots) und der Docstring des Skripts.

## Lizenz

GPL-3.0-or-later, siehe [`LICENSE`](LICENSE) und [ADR-0017](docs/adr/0017-license.md).
