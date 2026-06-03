# Georgia Power Large Load Economic Development Pipeline Dashboard

Interactive web dashboard for Georgia Power's large load pipeline data, sourced from quarterly reports filed under Docket 55378 (Q1 2024 - Q1 2026).

## Key Features

**Four tab views:**
- **Pipeline Snapshot** — Stacked bar chart of pipeline MW by planning year for a selected quarter
- **Pipeline Evolution** — Multi-quarter comparison, combining or separating by pipeline stage
- **Quarter-over-Quarter Changes** — Aggregate metrics (net MW, added/removed projects, schedule delays)
- **Snapshot by Vintage** — Projects broken down by age bucket (New, 2-3 qtrs, 4+ qtrs)

**Filters:** Report quarter, pipeline stage, segment (data center, manufacturing, etc.), vintage, planning year range.

**Load forecast overlays:** Selectable dashed reference lines from `GPC_Load_Forecasts.csv` — IRP large load projections and historical system peak demand — plotted alongside the stacked bars in Snapshot and Vintage views.

## Two Rendering Approaches

| Mode | File | How to run |
|------|-------|------------|
| **Static HTML** | `index.html` | Open in browser — fully self-contained, no server |
| **Redesigned static** | `index-redux.html` | Open in browser — same data, enhanced UI with KPI cards, branded header, styled badges |
| **Dash app** | `scripts/app.py` | `python scripts/app.py` → `http://localhost:8050` |

All three use the same underlying data. The Dash app computes data live from `outputs/combined/` CSVs. The static HTML files embed all data as inline JSON.

## Data Pipeline

```
inputs/workbooks/           # Raw Excel files per quarter (scraped)
inputs/2026Q1/              # Q1 2026 manual CSVs
         │
         ▼
scripts/build_dataset.py    # Normalize → combined CSV files
         │
         ▼
outputs/combined/
  ├── pipeline_projects.csv  # Project-level with load columns per year
  ├── pipeline_changes.csv   # QoQ change metrics
  └── pipeline_snapshot.csv  # Aggregated by (quarter, stage, year)
         │
         ▼
scripts/assign_project_ids.py  # Persistent project IDs across quarters
         │
         ▼
scripts/generate_site.py    # Inline JSON embedding → index.html + index-redux.html
         │
         ▼
index.html / index-redux.html  # Deployable — GitHub Pages ready
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scrape_workbooks.py` | Downloads quarterly Excel report files |
| `scripts/build_dataset.py` | Parses Excel/CSV → normalized combined datasets |
| `scripts/assign_project_ids.py` | Assigns persistent IDs to track projects across quarters |
| `scripts/generate_site.py` | Generates static `index.html` and `index-redux.html` with embedded JSON |
| `scripts/app.py` | Plotly Dash app (live server, same 4-tab layout) |
| `scripts/spot_check.py` / `spot_check2.py` | Validation scripts |

## File Structure

```
large-loads-reports/
├── index.html              # Static dashboard (generated)
├── index-redux.html        # Redesigned static dashboard (generated)
├── GPC_Load_Forecasts.csv  # Reference forecast series
├── assets/
│   ├── index.template.html       # Source template for index.html
│   ├── index-redux.template.html # Source template for index-redux.html
│   └── rmi_logo_horitzontal_no_tagline.svg
├── inputs/
│   ├── 2026Q1/             # Q1 2026 manual CSVs
│   └── workbooks/          # Quarterly Excel files
├── outputs/
│   └── combined/           # Normalized CSVs (generated)
├── scripts/                # All Python scripts
└── README.md
```

## Quick Start

```bash
# Regenerate static sites after data update
python scripts/generate_site.py

# Or run the live Dash app
python scripts/app.py
```

Open `index.html` or `index-redux.html` in any browser — no dependencies needed at runtime.