# ADR-0016: Report view — matplotlib-backed summary for the professor

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-PROF-INSIGHTS (the professor's motivation to use the app at all), US-PROF-TRENDS, US-PROF-COMPARE, US-PROF-NOTICE. Without this view, the MVP serves only US-RES-LOW-FRICTION — i.e. the professor has no reason to use the app beyond doing the researcher a favour.

## Decision

A "Report" view in the GUI, opened from a dedicated toolbar button placed **next to "Update stale"** in the toolbar. The button is **disabled** until at least one successful module run exists in the local source; it enables automatically when data becomes available and stays enabled thereafter.

The Report renders summary aggregates and charts over the current local data (theses with `source.kind='local'` AND `excluded=0`), using **matplotlib** with the Tk backend (`FigureCanvasTkAgg`).

## View placement

Opens as a **separate tab** in the main window (`ttk.Notebook`), peer to the Grid tab. User switches between Grid and Report tabs. Data is shared; the Report recomputes its aggregates on open and on `RunCompleted` events while it is the active tab.

## Content (MVP)

Single scrollable screen with five panels:

1. **Summary cards** (top strip): N theses analysed · N excluded · language mix · bachelor/master counts · year range · median word count.
2. **Length over time** (scatter): `word_count` vs publication year, colour-coded by `type`, with linear trend line. Reads US-PROF-TRENDS literally.
3. **Length by type** (box plots): `word_count` distribution for Bachelor vs Master. Reads US-PROF-COMPARE.
4. **Reading ease distribution** (histogram): `flesch_reading_ease`, faceted by language (en, de).
5. **Language mix** (bar chart): counts per language code.
6. **Notable theses** (list): 5–10 entries flagged as outliers on at least one trustworthy metric (`avg_word_len`, `std_sentence_len`, `yules_k`, `flesch_reading_ease`), each rendered as `<title> · <metrics it's an outlier on> · <handle>`. Reads US-PROF-NOTICE.

Linear axes throughout (per `feedback_no_log_scale` from the exploration phase).

## Dependency added

`matplotlib` (BSD-style, ~10 MB in the PyInstaller bundle). Already familiar to the team from the `exploration/` and `harvester/` scripts.

## Disabled state

```sql
SELECT COUNT(*) FROM v_current_metrics
WHERE status='ok' AND source_id IN (SELECT id FROM sources WHERE kind='local')
```

Returns 0 → button disabled, tooltip "Run analyses on at least one thesis to view the report." Returns ≥ 1 → button enabled.

## Privacy

The Report is a read-only local view. It does not transmit, export, or otherwise emit data. No new entries in `core/privacy_metadata.py`.

## Alternatives considered

- **Plotly** (interactive charts): JS-backed, awkward Tk integration, larger bundle. Rejected.
- **Custom Canvas drawing**: full control but ~10× more code for charts matplotlib gives us in one line. Rejected.
- **Separate window** (instead of a tab): would allow side-by-side viewing of Grid + Report. Considered but tabs are simpler; most professors look at one or the other.
- **No report in MVP**: contradicts US-PROF-INSIGHTS. The MVP would serve only the researcher's data-collection interest, with nothing for the professor to look at after clicking Run.

## Consequences

- ✅ The professor finally has a reason to open the app beyond contributing data.
- ✅ Matplotlib is mature, ubiquitous, and well-tested with Tk.
- ✅ The Report respects `excluded=1` theses (they're filtered out of aggregates).
- ✅ Re-render on `RunCompleted` events gives a live-updating feel while a batch is running.
- ⚠️ Matplotlib first-import is ~500 ms; mitigated by lazy import on Report-tab-open.
- ⚠️ PyInstaller bundle grows ~10 MB. Acceptable given ADR-0014's ~100 MB headline.
- ⚠️ Additional UI surface (charts) to maintain and translate when i18n lands.

## Revisit when

- MVP charts prove insufficient and we need interactive filtering / drill-down.
- A different chart library proves to integrate better with Tk.
- Professor feedback indicates the report should be downloadable as a PDF (out-of-MVP today).
