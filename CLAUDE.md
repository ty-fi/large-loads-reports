# CLAUDE.md — Project Guide for Agents

This document orients future agents to how the component parts of this repo work together. Read this before making significant changes.

## What this repo is

A web dashboard for **Georgia Power's Large Load Economic Development Pipeline** (Docket 55378, Q1 2024 – Q1 2026), built by RMI. Two delivery formats exist; the static one is the actively-maintained presentation surface, the Dash app is a secondary live-server version.

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
│   ├── workbooks/<quarter>/  # Raw Excel reports (Q1 2024 – Q4 2025)
│   ├── 2026Q1/               # Manual CSVs for Q1 2026 (no Excel available)
│   │   ├── pipeline_main.csv
│   │   ├── new_projects.csv
│   │   ├── pipeline_exits.csv
│   │   ├── load_changes.csv        # per-project load deltas with Change_MW
│   │   ├── stage_changes.csv       # per-project stage transitions
│   │   ├── service_date_changes.csv # per-project date deltas with Change_Months
│   │   └── load_ramp_comparison.csv
│   └── GPC_Load_Forecasts.csv       # IRP forecast reference series
├── outputs/combined/         # Normalized CSVs (generated, do NOT edit)
│   ├── pipeline_projects.csv       # 888 rows: per-project, per-quarter + load_2023..load_2037
│   ├── pipeline_changes.csv        # 9 rows: per-quarter aggregate change metrics
│   └── pipeline_snapshot.csv       # Aggregated by (quarter, stage, year)
├── scripts/
│   ├── scrape_workbooks.py    # Downloads quarterly Excel files from PSC site
│   ├── build_dataset.py       # Parses Excel + Q1 2026 CSVs → combined CSVs
│   ├── assign_project_ids.py  # Matches projects across quarters → persistent proj_id
│   ├── generate_site.py       # Reads combined CSVs → embeds JSON in template → index.html
│   ├── app.py                 # Plotly Dash app (live server, same 4-tab layout)
│   └── spot_check.py / spot_check2.py  # Validation
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
inputs/2026Q1/      │     (parse sheets,       ├──→  pipeline_changes.csv
  *.csv             ┘      normalize, join)    └──→  pipeline_snapshot.csv
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
- Parses Q1 2026 manual CSVs from `inputs/2026Q1/`
- Produces two outputs:
  - `pipeline_snapshot.csv`: long-format (quarter × stage × planning_year) → total MW
  - `pipeline_changes.csv`: per-quarter aggregate metrics (added/removed count + MW, load change net MW, stage changes count, avg delay months)
- Stage normalization via `STAGE_ALIASES` dict

### `scripts/assign_project_ids.py`
- Matches projects across quarters (fingerprint matching with multiple passes)
- Confidence values: `seed`, `exact`, `exact_noseg`, `ramp_0.XX`, `identity`, `identity_0.XX`, `new`
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
1. Drop the new Excel into `inputs/workbooks/<newQuarter>/` (or add manual CSVs to `inputs/<newQuarter>/`)
2. Add the new quarter to `QUARTER_ORDER` in `build_dataset.py` (line ~28) and in `assign_project_ids.py` (similar constant)
3. Run `python scripts/build_dataset.py` (rebuilds snapshot + changes CSVs)
4. Run `python scripts/assign_project_ids.py` (assigns persistent IDs)
5. Run `python scripts/generate_site.py` (regenerates index.html)
6. Commit and push (Render auto-deploys if used)

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

### Vintage colors (gradient per stage, light to dark for new to old)
- Technical Review: `#2E5F8A` → `#5B8DB8` → `#9BBDD8`
- Request for Service: `#C4711A` → `#E8963A` → `#F4BF87`
- Contract for Electric Service: `#2A7A55` → `#4CAF7D` → `#8ED4B0`

### Python environment
- A `.venv` at the repo root has Python 3.13 + pandas. Use `.venv\Scripts\python.exe scripts/generate_site.py` to regenerate.
- Created with `uv venv .venv --python 3.13 && uv pip install pandas --python .venv\Scripts\python.exe`
- Default `python` on PATH is 3.12 (no pandas) — always use the venv.

## Gotchas (things that aren't obvious)

1. **There are TWO different "stage color" sets documented.** `_SESSION-CONTEXT.md` says Contract=`#166534`, Request=`#92400e`, Review=`#475569` (the *old* badge colors for stage pills in tables). The actual chart bar colors are `#5B8DB8`, `#E8963A`, `#4CAF7D`. The template uses both — the lighter/more saturated ones for chart bars, the darker ones for `.badge-*` classes in tables.

2. **`__DATA_PLACEHOLDER__` is replaced as a raw string**, not parsed. If you add `</script>` anywhere in the embedded data, it'll break the HTML. Avoid strings containing `</script>` in CSVs (escape if needed).

3. **`renderChanges()` is a multi-branch function** with different render logic for different metrics. After a major redesign, consider splitting into separate render functions per metric, each with its own chart container — see `_QOQ-REDESIGN-CHECKLIST.md` for the in-progress refactor.

4. **The `Pipeline Evolution` y-axis title is dynamic** — it changes between `Total Pipeline MW (all stages)` and `Pipeline MW by Stage` depending on the aggregation mode radio button.

5. **The quarter animation y-axis is locked** to the final quarter's (2026Q1) peak for the *selected* stages, not the global max. This prevents unchecked stages from inflating the y-axis range.

6. **Project IDs are persistent across quarters** but the matching algorithm is heuristic. The `match_confidence` column tells you how confident the match is — when iterating on data, check this column for quality.

7. **`added` and `removed` arrays in `EMBEDDED` use the *current* quarter for the timestamp** even for removed projects (they're attributed to the quarter they disappeared from, not the quarter they were first seen).

8. **The `info-toggle` button is just a `<div>` toggle** — it doesn't have an aria-expanded attribute. Consider adding accessibility later.

9. **The `Pipeline Snapshot` and `Snapshot by Vintage` charts have an `Export this graph` button** that renders to a hidden off-screen div with larger fonts and a narrower 900px width, optimized for blog/website integration. See `exportGraphAsImage()` in `index.template.html` (search for it).

10. **Forecast line colors** are defined in `generate_site.py` (`_fc_desired` dict at line ~113). They are not in `meta`, so changing them requires editing the script.

## Things to NOT do

- **Don't edit `index.html` directly** — it's regenerated. Always edit `assets/index.template.html` and run `generate_site.py`.
- **Don't edit files in `outputs/combined/`** — they're generated by `build_dataset.py` + `assign_project_ids.py`.
- **Don't add secrets** to the repo (no API keys, no credentials).
- **Don't commit `_*.md` files to public repos** — they're gitignored via the convention in the global `~/.claude/CLAUDE.md`.

## See also

- `_SESSION-CONTEXT.md` — Current session state, at-a-glance, next steps
- `_QOQ-REDESIGN-CHECKLIST.md` — In-progress redesign of the QoQ tab
- `_RENDER-DEPLOY-PLAN.md` — Plan to deploy the Dash app to Render
- `README.md` — Public-facing overview
