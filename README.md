# Georgia Power Large Load Economic Development Pipeline Dashboard

Interactive web dashboard for Georgia Power's large load pipeline data, sourced from quarterly reports filed under Docket 55378 (Q1 2024 – Q2 2026). Built by RMI.

## Key Features

**Four tab views:**
- **Pipeline Snapshot** — Stacked bar chart of pipeline MW by planning year for a selected quarter
- **Pipeline Evolution** — Multi-quarter comparison with teal-to-navy color gradient, combining or separating by pipeline stage
- **Quarter-over-Quarter Changes** — Aggregate metrics (net MW, added/removed projects, schedule delays)
- **Snapshot by Vintage** — Projects broken down by age bucket (New, 2-3 qtrs, 4+ qtrs)

**Filters:** Horizontal pill-based filter bars for report quarter, pipeline stage, segment (data center, manufacturing, etc.), vintage, and planning year range. All/None toggles on every filter group.

**Load forecast overlays:** Selectable dashed reference lines from IRP filings — large load projections and historical system peak demand — plotted alongside the stacked bars in Snapshot and Vintage views.

**Table features:** Color-coded badges for pipeline stage, segment, and territory. Sortable columns. Client-side search filtering on the projects table.

## Data Pipeline

```
inputs/
  ├── workbooks/             # Raw Excel files per quarter (scraped)
  ├── 2026Q1/                # Q1 2026 manual CSVs (no Excel was filed)
  └── GPC_Load_Forecasts.csv # Reference forecast series
         │
         ▼
scripts/build_dataset.py     # Normalize → combined CSV files
scripts/assign_project_ids.py # Persistent project IDs across quarters
         │
         ▼
outputs/combined/
  ├── pipeline_projects.csv  # Project-level with load columns per year
  ├── pipeline_changes.csv   # QoQ change metrics
  └── pipeline_snapshot.csv  # Aggregated by (quarter, stage, year)
         │
         ▼
scripts/generate_site.py     # Embed JSON into template → index.html
         │
         ▼
index.html                   # Deployable — GitHub Pages ready
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scrape_workbooks.py` | Downloads quarterly Excel report files |
| `scripts/build_dataset.py` | Parses Excel/CSV → normalized combined datasets |
| `scripts/assign_project_ids.py` | Assigns persistent IDs to track projects across quarters |
| `scripts/generate_site.py` | Generates `index.html` with embedded JSON from template |
| `scripts/app.py` | Plotly Dash app (live server, same 4-tab layout) |
| `scripts/spot_check.py` / `spot_check2.py` | Validation scripts |

## File Structure

```
large-loads-reports/
├── index.html                # Static dashboard (generated)
├── assets/
│   ├── index.template.html   # Source template for index.html
│   └── rmi_logo_horitzontal_no_tagline.svg
├── inputs/
│   ├── 2026Q1/               # Q1 2026 manual CSVs (no Excel was filed)
│   ├── workbooks/            # Quarterly Excel files
│   └── GPC_Load_Forecasts.csv # Reference forecast series
├── outputs/
│   └── combined/             # Normalized CSVs (generated)
├── scripts/                  # All Python scripts
└── README.md
```

## Quick Start

```bash
# Regenerate static site after data update
python scripts/generate_site.py

# Or run the live Dash app
python scripts/app.py
```

Open `index.html` in any browser — no dependencies needed at runtime.
