# User Stories

Identifier format: `US-<persona>-<short>`.

Personas: `PROF` (professor), `PWR` (power user), `RES` (researcher / project team).

## Professor (primary persona)

| ID | Story |
|---|---|
| **US-PROF-INSIGHTS** | As a professor I want to see interesting insights about my collection of theses — patterns, trends, outliers — that I wouldn't have noticed by reading them individually, so the analysis is worth the time I spent setting it up and I have a reason to come back. |
| **US-PROF-TRENDS** | As a professor I want to see how characteristics of theses in my department have changed over the years, so I can spot real generational shifts in writing. |
| **US-PROF-COMPARE** | As a professor I want to compare bachelor and master theses in my collection side-by-side, so I can see whether the step up in degree level shows up in the writing. |
| **US-PROF-NOTICE** | As a professor I want unusual theses in my collection surfaced to me, so I can decide whether to give them a second look. |
| **US-PROF-AUTO-OPEN** | As a professor, the application remembers my project across runs and re-opens it automatically, so I don't have to think about where data is stored. |
| **US-PROF-NO-TRACES** | As a professor, I want every file the application creates to live inside the one project folder I chose, with nothing written elsewhere on my machine, so that deleting that folder removes the application's data and every trace of it. |
| **US-PROF-ATTRS** | As a professor I want to add attributes to files when adding them (e.g. the type of thesis: bachelor, master), so the analyses can be grouped meaningfully. |
| **US-PROF-EXCLUDE** | As a professor I want to exclude certain files from all analyses, to protect theses with a confidential clause. |
| **US-PROF-SELECT** | As a professor I want to select which analyses are run, since I might have reservations against some of the metrics for reasons. |
| **US-PROF-EXPLAIN** | As a professor I want to read an explanation of what I see, to understand which data I share. → Help pages with cross-references; each metric needs an explaining help page. |
| **US-PROF-EXPORT** | As a professor I want to export the results into a single file, so that I can easily send back my results to the research team. |
| **US-PROF-QUALITY** | As a professor I want corrupted text extractions flagged in the grid so I don't draw conclusions from gibberish. |
| **US-PROF-RERUN** | As a professor I want to re-run all analyses on demand, in case I've added new files or changed settings. |
| **US-PROF-UPDATE** | As a professor I want to update only the analyses whose modules or upstream metrics have changed, without re-running everything. |
| **US-PROF-DOUBLECLICK** | As a professor I want to double-click an artefact icon in the data grid and see the underlying file. |
| **US-PROF-SORT** | As a professor I want the data grid to be sortable by clicking the column headers. |
| **US-PROF-SEARCH** | As a professor I want fuzzy search on grid columns. |

## Power user (extended-mode persona)

| ID | Story |
|---|---|
| **US-PWR-EXTENDED** | As a power user I want to see more detailed metrics and have more settings to tinker with than a normal professor. → Extended mode in settings. |
| **US-PWR-PRODUCER** | As a power user I want to choose which producer module supplies each artefact kind (e.g. which PDF extractor) for a given run. |
| **US-PWR-SCHEME** | As a power user I want to switch between different outlier highlighting schemes. |

## Researcher (project team)

| ID | Story |
|---|---|
| **US-RES-LOW-FRICTION** | As a researcher I want professors to be able to complete the contribute-data loop in five simple steps (start → select → run → export → send), so that friction is low enough that they actually do it and we get the data back for our research. |
| **US-RES-CLI** | As a researcher, I want to be able to run analyses quickly from the CLI and use the graphical UI only as a viewer of the results, to iterate quickly while developing modules and have a solid testing interface. |
| **US-RES-OUTLIERS** | As a researcher I want to be able to quickly identify outliers in my data to further investigate them. → The cells with outliers are highlighted. |
| **US-RES-LANG** | As a researcher I want to know in which language a thesis was written, to apply the metrics properly. → Language classifier module. |
| **US-RES-IMPORT** | As a researcher I want to easily import multiple exports from professors into my database, to analyse the combined data as a whole and grouped by source. |
| **US-RES-LOCAL-RERUN** | As a researcher running this tool on my own machine, I want analyses to run on my own theses normally while imported data from professors stays read-only, so I can build a local working copy without losing the cross-cohort context. |
| **US-RES-COMPARE** | As a researcher I want to compare results of different text-extraction libraries against each other, since artefact and metric values may depend on the extractor used. |

## Cross-cutting (any persona)

| ID | Story |
|---|---|
| **US-ALL-OFFLINE** | As any user I want the application to run fully offline, with no data leaving my machine unless I explicitly export. |
| **US-ALL-PRIVACY** | As any user I want a clear privacy statement that explains exactly what data the application processes, stores, and exports. |
| **US-ALL-TOOLTIPS** | **Deferred, and restated.** As any user I want an explanation of what a cell or column represents, available *on demand* rather than on hover. -> A cell's state and reason are explained by the details panel (SDD 9.9), and a column's meaning by its help page (SDD 9.4, ADR-0012). The original hover-tooltip form shipped (#25) and was removed again (#66): the one genuinely oversized payload, a full traceback, does not belong in a hover popup, and the widget itself flickered under Linux/WSLg (#48). Whether an on-hover affordance returns in a narrower form is undecided -- this story may yet be dropped outright rather than re-satisfied. |
