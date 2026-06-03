"""
Generates a self-contained static HTML page with Plotly.js charts
for the Georgia Power Large Load Economic Development Pipeline.
Embeds all data as JSON — no server needed.
Output: index.html
"""
import json
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).parent
COMBINED_DIR = SCRIPT_DIR.parent / "outputs" / "combined"
ROOT = SCRIPT_DIR.parent / "index.html"
ROOT_TEMPLATE_FILE = SCRIPT_DIR.parent / "assets" / "index.template.html"
ROOT_TEMPLATE = ROOT_TEMPLATE_FILE.read_text(encoding="utf-8") if ROOT_TEMPLATE_FILE.exists() else None

df_proj = pd.read_csv(COMBINED_DIR / "pipeline_projects.csv")
df_changes = pd.read_csv(COMBINED_DIR / "pipeline_changes.csv")
df_changes["net_mw"] = df_changes["added_mw"].fillna(0) - df_changes["removed_mw"].fillna(0)

LOAD_COLS = [c for c in df_proj.columns if c.startswith("load_")]
ID_COLS = [
    "proj_id", "report_quarter", "project_stage", "segment",
    "project_age", "announced_load_mw", "territory",
    "initial_service_date", "match_confidence",
]

df_long = df_proj.melt(
    id_vars=ID_COLS,
    value_vars=LOAD_COLS,
    var_name="year_col",
    value_name="load_mw",
)
df_long["planning_year"] = df_long["year_col"].str.extract(r"(\d{4})").astype(int)
df_long = df_long.drop(columns=["year_col"])
df_long = df_long[df_long["load_mw"].notna() & (df_long["load_mw"] > 0)]

QUARTER_ORDER = [
    "2024Q1", "2024Q2", "2024Q3", "2024Q4",
    "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1",
]
QUARTERS_PRESENT_ALL = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique()]
QUARTERS_PRESENT = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique() and q != "2024Q1"]
ALL_YEARS = sorted(int(y) for y in df_long["planning_year"].unique())
ALL_SEGMENTS = sorted(s for s in df_long["segment"].dropna().unique().tolist() if s)
ALL_STAGES = ["Technical Review", "Request for Service", "Contract for Electric Service"]
STAGE_COLORS = {
    "Technical Review": "#5B8DB8",
    "Request for Service": "#E8963A",
    "Contract for Electric Service": "#4CAF7D",
}
VINTAGE_COLORS = {
    "Technical Review":              ["#2E5F8A", "#5B8DB8", "#9BBDD8"],
    "Request for Service":           ["#C4711A", "#E8963A", "#F4BF87"],
    "Contract for Electric Service": ["#2A7A55", "#4CAF7D", "#8ED4B0"],
}

_PROJ_FLOW = df_proj[["proj_id", "report_quarter", "project_stage",
                        "project_age", "announced_load_mw", "segment"]].copy()

df_added = _PROJ_FLOW[
    (_PROJ_FLOW["project_age"] == 1) & (_PROJ_FLOW["report_quarter"] != "2024Q1")
].copy()

_removed_rows = []
for i in range(1, len(QUARTERS_PRESENT_ALL)):
    prev_q = QUARTERS_PRESENT_ALL[i - 1]
    curr_q = QUARTERS_PRESENT_ALL[i]
    prev_ids = set(df_proj[df_proj["report_quarter"] == prev_q]["proj_id"])
    curr_ids = set(df_proj[df_proj["report_quarter"] == curr_q]["proj_id"])
    gone = prev_ids - curr_ids
    if gone:
        rows = _PROJ_FLOW[
            (_PROJ_FLOW["proj_id"].isin(gone)) &
            (_PROJ_FLOW["report_quarter"] == prev_q)
        ].copy()
        rows["report_quarter"] = curr_q
        _removed_rows.append(rows)

df_removed = pd.concat(_removed_rows, ignore_index=True) if _removed_rows else pd.DataFrame(columns=_PROJ_FLOW.columns)


def _vintage_bucket(age):
    if age == 1:
        return 2
    if age <= 3:
        return 1
    return 0


_VINT_IDX_TO_LABEL = {0: "4+ qtrs", 1: "2-3 qtrs", 2: "New (1 qtr)"}
for _df in (df_added, df_removed):
    if not _df.empty:
        _df["vintage_idx"] = _df["project_age"].apply(_vintage_bucket)
        _df["vintage_label"] = _df["vintage_idx"].map(_VINT_IDX_TO_LABEL)

VINTAGE_LABELS = ["New (1 qtr)", "2-3 qtrs", "4+ qtrs"]

METRIC_LABELS = {
    "net_mw": "Net MW Added (new projects - removed)",
    "load_change_net_mw": "Load Changes Net MW",
    "added_projects": "Projects Added (count)",
    "added_mw": "Projects Added (MW)",
    "removed_projects": "Projects Removed (count)",
    "removed_mw": "Projects Removed (MW)",
    "stage_changes_count": "Stage Changes (count)",
    "avg_delay_months": "Average Schedule Delay (months)",
}

# Load GPC load forecasts for reference line overlays
df_fc = pd.read_csv(SCRIPT_DIR.parent / "inputs" / "GPC_Load_Forecasts.csv")
_fc_desired = {
    "2023-IRP-update-w-LRM-minus-2023-IRP-base": "#d32f2f",
    "2025-IRP-base-minus-2023-IRP-base": "#1976d2",
    "GPC-all-system-peak-demand": "#757575",
}
_load_cols = [c for c in df_fc.columns if c.startswith("load_")]
for col in _load_cols:
    df_fc[col] = df_fc[col].apply(lambda x: float(str(x).replace(',', '').replace('"', '')) if pd.notna(x) else 0.0)

forecast_data = []
for _, row in df_fc.iterrows():
    fid = row["forecast"]
    if fid not in _fc_desired:
        continue
    title = str(row.get("graphing title", "") or fid).replace('"""', '').replace('"', '').strip()
    years_dict = {int(c.replace("load_", "")): row[c] for c in _load_cols}
    x_vals = sorted(years_dict.keys())
    forecast_data.append({
        "id": fid,
        "title": title,
        "color": _fc_desired[fid],
        "x": x_vals,
        "y": [years_dict[y] for y in x_vals],
    })

table_data = df_proj[[
    "proj_id", "report_quarter", "project_stage", "segment", "territory",
    "announced_load_mw", "initial_service_date", "project_age", "match_confidence",
]].to_dict("records")

EMBEDDED = {
    "long": df_long.to_dict("records"),
    "changes": df_changes.to_dict("records"),
    "table": table_data,
    "added": df_added.to_dict("records") if not df_added.empty else [],
    "removed": df_removed.to_dict("records") if not df_removed.empty else [],
    "forecasts": forecast_data,
    "meta": {
        "quarters": QUARTERS_PRESENT,
        "years": ALL_YEARS,
        "segments": ALL_SEGMENTS,
        "stages": ALL_STAGES,
        "vintage_labels": VINTAGE_LABELS,
        "stage_colors": STAGE_COLORS,
        "vintage_colors": VINTAGE_COLORS,
        "metric_labels": METRIC_LABELS,
        "forecast_labels": {f["id"]: f["title"] for f in forecast_data},
    },
}



def main():
    if ROOT_TEMPLATE:
        html = ROOT_TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(EMBEDDED, indent=None, ensure_ascii=False, default=str))
        ROOT.write_text(html, encoding="utf-8")
        print(f"Generated {ROOT} ({ROOT.stat().st_size:,} bytes)")
    else:
        print("WARNING: index.template.html not found, skipping index.html generation")

    print(f"  Rows: long={len(EMBEDDED['long'])}, changes={len(EMBEDDED['changes'])}, table={len(EMBEDDED['table'])}")
    print(f"  Added: {len(EMBEDDED['added'])}, Removed: {len(EMBEDDED['removed'])}")
    print(f"  Forecasts: {len(EMBEDDED['forecasts'])}, Quarters: {len(EMBEDDED['meta']['quarters'])}, Years: {len(EMBEDDED['meta']['years'])}")


if __name__ == "__main__":
    main()