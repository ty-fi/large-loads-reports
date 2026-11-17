# CLAUDE.md — Project Guide for Agents

This document orients future agents to how the component parts of this repo work together. Read this before making significant changes.

## What this repo is

A web dashboard for **Georgia Power's Large Load Economic Development Pipeline** (Docket 55378, Q1 2024 – Q3 2026), built by RMI. Two delivery formats exist; the static one is the actively-maintained presentation surface, the Dash app is a secondary live-server version.

## The two output formats

| Format | File | Source | Maintained? |
|---|---|---|---|
| **Static** (primary) | `index.html` | `assets/index.template.html` + `scripts/generate_site.py` | Yes — iterate here for presentation changes |
| **Live server** (secondary) | `scripts/app.py` | Standalone Plotly Dash app | No — kept for parity but not the focus |

**Decision rule:** if the user says "let's keep iterating on the presentation" or asks for visual/UX changes, edit the static side. If they specifically mention the Dash app, edit `scripts/app.py`.

## Repository structure

```
large-loads-reports/
├── index.html                # Generated static dashboard (do NOT edit directly)
├── assets/
│   ├── index.template.html   # Source-of-truth for static dashboard
│   └── rmi_logo_horitzontal_no_tagline.svg
├── inputs/
│   ├── workbooks/<quarter>/  # Georgia Power's Excel attachment, one per quarter (Q1 2024 – Q3 2026)
│   └── GPC_Load_Forecasts.csv       # IRP forecast reference series
├── outputs/combined/         # Normalized CSVs (generated, do NOT edit)
│   ├── pipeline_projects.csv       # 1,131 rows: per-project, per-quarter + load_2023..load_2037
│   ├── pipeline_changes.csv        # 11 rows: per-quarter aggregate change metrics
│   └── pipeline_snapshot.csv       # Aggregated by (quarter, stage, year)
├── scripts/
│   ├── scrape_workbooks.py    # Downloads quarterly Excel files from PSC site
│   ├── build_dataset.py       # Parses Excel workbooks → combined CSVs
│   ├── assign_project_ids.py  # Matches projects across quarters → persistent proj_id
│   ├── generate_site.py       # Reads combined CSVs → embeds JSON in template → index.html
│   └── app.py                 # Plotly Dash app (live server, same 4-tab layout)
├── README.md                  # Public readme
└── _*.md                      # Underscore-prefixed: Claude-managed session/task files
    ├── _SESSION-CONTEXT.md
    ├── _RENDER-DEPLOY-PLAN.md
    ├── _QOQ-REDESIGN-CHECKLIST.md
    └── _context-history/      # Older session contexts
```

## Data flow (the critical mental model)

```
Raw inputs              Build pipeline                Combined outputs         Template injection
─────────────           ───────────────               ────────────────         ─────────────────
inputs/workbooks/   ┐
  <quarter>/*.xlsx  ├──→  build_dataset.py     ┌──→  pipeline_projects.csv
                    │     (parse sheets,       ├──→  pipeline_changes.csv
                    ┘      normalize, join)    └──→  pipeline_snapshot.csv
                                              │
                                              ▼
                              assign_project_ids.py
                              (cross-quarter matching,
                              persistent proj_id)
                                              │
                                              ▼
                                  generate_site.py
                                  (read CSVs, build
                                   per-tab data, embed
                                   as JSON in template)
                                              │
                                              ▼
                                       index.html
                                       (single self-contained
                                        file, Plotly.js + data)
```

**Key insight:** the static dashboard is a single HTML file with all data embedded as JSON. No backend, no API calls, just Plotly.js rendering in the browser. The template has a single `__DATA_PLACEHOLDER__` that gets replaced.

## Per-file responsibilities

### `scripts/build_dataset.py`
- Parses Excel workbooks in `inputs/workbooks/<quarter>/` (one .xlsx per quarter)
- Produces two outputs:
  - `pipeline_snapshot.csv`: long-format (quarter × stage × planning_year) → total MW
  - `pipeline_changes.csv`: per-quarter aggregate metrics (added/removed count + MW, load change net MW, stage changes count, avg delay months)
- Stage normalization via `STAGE_ALIASES` dict

### `scripts/assign_project_ids.py`
- Matches projects across quarters with one min-cost assignment per quarter
  (`scipy.optimize.linear_sum_assignment`), driven by each filing's own
  New Project? / change flags and its change sheets — see gotcha 16
- Confidence values: `seed`, `new`, `exact` (every attribute reconciles with the
  filing), `high` (minor disagreement), `low` (a substantive attribute disagrees)
- Output: `pipeline_projects.csv` (with `proj_id` column)

### `scripts/generate_site.py` (most-edited script)
- Reads `outputs/combined/*.csv` (NOT the raw inputs)
- Reshapes data into structures each render function needs:
  - `df_long`: long-format with `planning_year` extracted from `load_YYYY` columns
  - `df_changes`: per-quarter change aggregates
  - `df_added` / `df_removed`: per-project added/removed lists (already computed)
  - Forecasts: 3 series from `inputs/GPC_Load_Forecasts.csv`
  - **EMBEDDED dict**: the final JSON payload injected into the template
- Runs `Plotly`-equivalent logic in Python to compute derived data (added/removed by stage × vintage, Sankey flows, histograms) so the browser just renders

### `assets/index.template.html`
- The single source of truth for the static dashboard
- Structure: HTML shell → CSS (in `<style>`) → data placeholder → inline `<script>` with all render functions
- `__DATA_PLACEHOLDER__` is the only substitution point
- 4 tabs: `snapshot` (Pipeline Snapshot), `evolution` (Pipeline Evolution), `changes` (QoQ Changes), `vintage` (Snapshot by Vintage)
- Each tab has its own filter bar (pill checkboxes, dropdowns), main chart, optional sub-tables

### `scripts/app.py`
- Standalone Plotly Dash app, mirrors the 4-tab layout
- Less polished than the static version; intended for parity but secondary
- Uses `dcc.Store` + `dcc.Interval` for the quarter animation
- Run with `python scripts/app.py`

## Key data structures (embedded in `EMBEDDED`)

```python
EMBEDDED = {
    "long": [...],          # [{report_quarter, planning_year, project_stage, segment, load_mw, proj_id, ...}]
                            #   — 10,178 rows; melted from load_YYYY columns
    "changes": [...],       # per-quarter change aggregates (legacy)
    "table": [...],         # [{proj_id, report_quarter, project_stage, segment, territory, announced_load_mw, ...}]
    "added": [...],         # new projects per quarter with vintage
    "removed": [...],       # projects that existed prev quarter but not current, tagged with current quarter
    "forecasts": [...],     # 3 IRP forecast series
    "meta": {
        "quarters": [...], "years": [...], "segments": [...], "stages": [...],
        "stage_colors": {...}, "vintage_colors": {...},
        "metric_labels": {...}, "forecast_labels": {...},
    }
}
```

## Common tasks

### Add a new filter to a tab
1. Add the HTML element to the filter bar in `assets/index.template.html` (find the relevant tab div)
2. Add a `buildCheckboxes()` / `buildSelect()` call in the init section
3. Wire the change handler to call the relevant `render*()` function
4. If it affects the data structure, also update `generate_site.py` and `EMBEDDED`

### Add a new visualization
1. In `generate_site.py`: compute and add the new data to `EMBEDDED`
2. In `assets/index.template.html`: add a chart container `<div id="my-chart">` and a `renderMyChart()` function
3. Call the render function from the appropriate trigger (tab switch, filter change, init)
4. Run `python scripts/generate_site.py` to regenerate `index.html`
5. Test in browser

### Update with new quarterly data
Filings live at `https://psc.ga.gov/search/facts-document/?documentId=<docId>`
under Docket 55378. The Excel workbook is usually inside a single ZIP attachment,
but some filings attach it directly beside the PDF and Word files (Q1 2026 did);
`scrape_workbooks.py` handles both. A filing's attachments can also change after
the filing date: the Q1 2026 workbook was once believed missing and hand-
transcribed from the PDF, and that transcription had 63 wrong cells.
The docket page renders its document list with JavaScript, so find new docIds
from the JSON endpoint it calls (newest first):
`https://psc.ga.gov/search/service-facts-docket/?docketId=55378&sortDirection=desc&sortColumn=documentId&searchText=&pageSize=15&pageNumber=1`.
Add the docId to `FILINGS` in `scrape_workbooks.py`.

1. Run `scrape_workbooks.py`, or drop the new Excel into
   `inputs/workbooks/<newQuarter>/`. If a filing seems to have no workbook,
   check every attachment and re-check later before transcribing anything
   by hand
2. Add the new quarter to `QUARTER_ORDER` in **all four** of `build_dataset.py`,
   `assign_project_ids.py`, `generate_site.py`, and `app.py`
3. Run `.venv\Scripts\python.exe scripts/build_dataset.py`
4. Run `.venv\Scripts\python.exe scripts/assign_project_ids.py`
5. Run `.venv\Scripts\python.exe scripts/generate_site.py`
6. Commit and push — GitHub Pages builds from `main:/` and serves
   https://ty-fi.github.io/large-loads-reports/

**Validate before committing** — the filing format drifts between quarters
(see gotcha 10), and the failures are silent:
- the per-quarter table from `build_dataset.py` should show only the three real
  stages, and no `WARNING: ignoring unrecognized Project Stage value`
  you haven't already accounted for
- the new row in `pipeline_changes.csv` should not be all zeros
- the match summary from `assign_project_ids.py` should show `Exact` for most
  continuing projects, `New` equal to the New Project? flag count, `Removed`
  equal to the Removed Projects row count, and `Vanish` at 0. A `NOTE: filing
  does not reconcile` line, many `Low` matches, or nonzero `Vanish` means a
  field changed format or the filing has a bookkeeping error worth reading
- `generate_site.py` is deterministic: running it twice must produce an
  identical `index.html`

### Edit the static dashboard
**Never edit `index.html` directly** — it's regenerated. Edit `assets/index.template.html`, then run `python scripts/generate_site.py`.

## Conventions

### Naming
- Files/dirs: `snake_case` for Python, `kebab-case` for HTML/CSS classes
- Function names: `camelCase` in JS, `snake_case` in Python
- CSS variables: `--rmi-teal`, `--rmi-navy`, `--rmi-navy-deep` in `:root`

### Brand colors (RMI)
- Teal: `#56c4c4`
- Navy: `#123c63`
- Deep navy: `#1c355e`

### Stage colors (per current code — see "Gotchas" below)
- Technical Review: `#9bcce3` (light blue)
- Request for Service: `#529cba` (mid blue)
- Contract for Electric Service: `#005d7f` (dark navy blue)

### Vintage labels
- `New (1 qtr)` — project_age == 1
- `2-3 qtrs` — project_age 2 or 3
- `4+ qtrs` — project_age >= 4

`project_age` counts the quarterly reports a project has appeared in so far. Two
index conventions exist and must not be mixed: Python's `vintage_bucket()` uses
0 = 4+ (mapped through `VINTAGE_IDX_TO_LABEL`), while the template's
`vintBucket()` indexes `VINTAGE_LABELS` directly (0 = New). Mixing them swapped
New and 4+ on the Vintage tab until Nov 2026.

### Quarter colors (Pipeline Evolution lines)
The chart has a "Line colors" toggle above it. **Time ramp** (default) is
described below. **Distinct** uses the dataviz skill's 8-hue categorical palette
(`DISTINCT_HUES` in the template) in its validated order, repeating hues with a
different marker shape past 8 quarters. **Shuffle colors** draws random
assignments but rejects any that put a pair from `WEAK_HUE_PAIRS` (pairs that
fail the validator's CVD / normal-vision checks on `#fafafa`), or the same hue,
on quarters adjacent in time. Re-validate both lists if the palette changes.

Time ramp:
Generated by `quarter_ramp()` in `generate_site.py` and passed through
`meta.quarter_colors` — not hardcoded, and not computed in the template.
Monotone OKLCh lightness 0.74 → 0.26 (oldest → newest, so the newest quarter
stays darkest) with 240° of hue travel: green → teal → blue → purple → maroon.
Chroma is requested at 0.19 and clamped into sRGB per step.

### Vintage colors (one hue family per stage; New → 2-3 → 4+ runs dark → light)
`VINTAGE_COLORS` in `generate_site.py` (also used by the removed-by-vintage
bars on the Changes tab):
- Technical Review (aqua): `#006337` → `#009655` → `#00cb75`
- Request for Service (orange): `#913100` → `#d25117` → `#ff885c`
- Contract for Electric Service (blue): `#0053a6` → `#3280de` → `#74b0ff`
Validated with the dataviz skill's validator (see the comment there); re-run it
before changing any step.

### Python environment
- A `.venv` at the repo root has Python 3.13 + pandas + openpyxl + scipy. Use `.venv\Scripts\python.exe scripts/generate_site.py` to regenerate.
- Created with `uv venv .venv --python 3.13 && uv pip install pandas openpyxl scipy requests --python .venv\Scripts\python.exe`
- `requests` is needed only by `scrape_workbooks.py`.
- `scipy` is required by `assign_project_ids.py` (`linear_sum_assignment`).
- `openpyxl` is required by `build_dataset.py` and `assign_project_ids.py` to read the quarterly workbooks.
- Default `python` on PATH is 3.12 (no pandas) — always use the venv.

## Gotchas (things that aren't obvious)

1. **There are TWO different "stage color" sets documented.** `_SESSION-CONTEXT.md` says Contract=`#166534`, Request=`#92400e`, Review=`#475569` (the *old* badge colors for stage pills in tables). The actual chart bar colors are `#5B8DB8`, `#E8963A`, `#4CAF7D`. The template uses both — the lighter/more saturated ones for chart bars, the darker ones for `.badge-*` classes in tables.

2. **`__DATA_PLACEHOLDER__` is replaced as a raw string**, not parsed. If you add `</script>` anywhere in the embedded data, it'll break the HTML. Avoid strings containing `</script>` in CSVs (escape if needed).

3. **`renderChanges()` is a multi-branch function** with different render logic for different metrics. After a major redesign, consider splitting into separate render functions per metric, each with its own chart container — see `_QOQ-REDESIGN-CHECKLIST.md` for the in-progress refactor.

4. **The `Pipeline Evolution` y-axis title is dynamic** — it changes between `Total Pipeline MW (all stages)` and `Pipeline MW by Stage` depending on the aggregation mode radio button.

5. **The quarter animation y-axis is locked** to the final quarter's peak for the *selected* stages, not the global max. This prevents unchecked stages from inflating the y-axis range.

6. **Project IDs are persistent across quarters** but inferred (names are redacted; see gotcha 16). The `match_confidence` column tells you how confident the match is — when iterating on data, check this column for quality.

7. **`added` and `removed` arrays in `EMBEDDED` use the *current* quarter for the timestamp** even for removed projects (they're attributed to the quarter they disappeared from, not the quarter they were first seen).

8. **The `info-toggle` button is just a `<div>` toggle** — it doesn't have an aria-expanded attribute. Consider adding accessibility later.

9. **The `Pipeline Snapshot` and `Snapshot by Vintage` charts have an `Export this graph` button** that renders to a hidden off-screen div with larger fonts and a narrower 900px width, optimized for blog/website integration. See `exportGraphAsImage()` in `index.template.html` (search for it). The Snapshot
   tab also has `Export animation (GIF)` (`exportSnapshotGif()`): it renders
   every quarter with the current filters through the same pipeline
   (`buildSnapshotFigure()` → `buildExportLayout()` → `rasterizeFigure()`), adds
   eased in-between frames, and encodes in the browser with `gifenc`, loaded from
   jsDelivr on first click. Timing comes from `ANIM_STEP_MS` /
   `ANIM_TRANSITION_MS`, which also drive the on-screen Animate button (750 /
   400 ms; the Dash app's interval mirrors them). Exports fetch the Interstate
   fonts from `assets/`, so test them over HTTP, not `file://`.

10. **Filing formats drift between quarters, and the parsers now absorb it.**
    The Q2 2026 workbook changed four things at once, each of which silently
    corrupted the build before it was handled:
    - a trailing **footnote row** whose text landed in the Project Stage column
      (became a phantom stage) → `valid_stage()` / `norm_stage()` reject any
      value that is not a known stage, and warn rather than drop silently;
    - a **leading blank column** on every change sheet, which shifted the
      positional `row[0]/[1]/[2]` reads and zeroed out every change metric
      → parsers now anchor on the Project Name column (`name_col_index()`,
      `name_base()`);
    - **in-service dates as real Excel datetimes** (`2027-12-01`) instead of
      `Q4 2027` text, which broke every cross-quarter fingerprint match
      (0 exact matches) → `norm_date()` accepts datetimes and ISO dates;
    - a **negated sign** on the `Change (Months)` column → the delay metric is
      now derived from the two date columns instead of that column, so a
      future sign flip cannot invert it.
    When adding a quarter, check the per-quarter match summary from
    `assign_project_ids.py`: a quarter with few `Exact` matches means a
    matched field changed format.

11. **Chart date ranges and the default quarter are derived, not hardcoded.**
    `meta.quarter_range` (from `QUARTER_RANGE_LABEL` in `generate_site.py`)
    feeds all chart titles and the header; the Snapshot/Vintage quarter selects
    default to `LATEST_QUARTER`. Do not reintroduce literal quarter strings.

12. **The Sankey grid build is order-stable.** `_grid_links` is emitted via
    `sorted(_grid_flows.items())` because the upstream set iteration made the
    link order vary between runs, producing a spurious `index.html` diff on
    every regeneration.

13. **The Evolution quarter ramp has a series budget.** A single-hue ramp
    cannot separate this many ordered lines: holding the lightest step at the
    2:1 contrast floor caps lightness near L=0.74, which leaves only
    dL ~= 0.055 (dE ~= 5.5) per step at nine quarters. The current ramp spends
    240° of hue to reach a worst adjacent **and** worst all-pairs dE of 8.7 at
    N=9 (the old teal→navy ramp managed 4.9, with its lightest step at 1.99:1
    contrast — invisible on the `#fafafa` plot). Separation falls as quarters
    accumulate: ~7.5 at N=10, ~6.2 at N=12, ~5.2 at N=14, where it is back to
    the old ramp's legibility. Past roughly a dozen quarters the fix is fewer
    lines on one chart (facet by stage, or a decade/era grouping), not more hue.
    Verify with the dataviz skill's validator rather than by eye.

14. **Forecast line colors** are defined in `generate_site.py` (`_fc_desired` dict at line ~113). They are not in `meta`, so changing them requires editing the script.

15. **Change sheets put totals and footnotes in the Project Name column.**
    `Total` rows (carrying the column sum), `Note 1 - ...` rows, and footnotes
    (`*Announced load as of 2037`, `1. Absent customer ...`) all sit in the
    name column. Before Q3 2026 they were counted as projects, so added/removed
    counts ran 1–2 high in most quarters and added/removed/net-load MW doubled
    in 2025Q2, 2025Q3, 2025Q4 and 2026Q2. `is_project_row()` in both
    `build_dataset.py` and `assign_project_ids.py` now rejects them; extend its
    regex if a new kind of non-project row appears.

16. **`proj_id` matching is an assignment problem, not fingerprinting.** Names
    are redacted, but each filing's bookkeeping reconciles exactly:
    `prev − Removed Projects + (New Project? = Y) == current` in every quarter
    except two, both off by one on the same 216 MW Request for Service
    project: 2026Q1's Main sheet forgets to flag it new (Projects Added lists
    it), and 2026Q3 flags it new again (absent from Projects Added; it is an
    unflagged one-year date slip). Each
    current row also flags which of load / ramp / stage / date changed, and the
    change sheets give the prior values. `match_quarter()` turns that into a
    cost matrix (weights are the `W_*` / `COST_*` constants) and solves it.
    Validate by comparing the changes the matches imply against the change
    sheets' row counts; across 2024Q2–2026Q3 they are 86 / 253 / 26 implied
    load / date / stage changes against 75 / 247 / 23 listed. The previous
    multi-pass fingerprint + ramp-similarity matcher implied 281 / 289 / 71
    and attached about half of each quarter's new projects to old IDs.
    Known filing quirks it absorbs: 2025Q3 (revised filing) changed ~40 ramps
    and ~10 loads without setting the flags, and flags one unchanged 146 MW
    project as new; 2024Q4, 2025Q4 and 2026Q3 each carry a few unflagged
    in-service date rewrites.

## Things to NOT do

- **Don't edit `index.html` directly** — it's regenerated. Always edit `assets/index.template.html` and run `generate_site.py`.
- **Don't edit files in `outputs/combined/`** — they're generated by `build_dataset.py` + `assign_project_ids.py`.
- **Don't add secrets** to the repo (no API keys, no credentials).
- **Don't commit `_*.md` files to public repos** — they're gitignored via the convention in the global `~/.claude/CLAUDE.md`.

## See also

- `README.md` — Public-facing overview

Underscore-prefixed `_*.md` session files are gitignored and none currently
exist in this repo; create them only if a session actually needs one.
