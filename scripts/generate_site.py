"""
Generates a self-contained static HTML page with Plotly.js charts
for the Georgia Power Large Load Economic Development Pipeline.
Embeds all data as JSON — no server needed.
Output: index.html
"""
import json
import math
import re
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).parent
COMBINED_DIR = SCRIPT_DIR.parent / "outputs" / "combined"
INPUTS_DIR = SCRIPT_DIR.parent / "inputs"
ROOT = SCRIPT_DIR.parent / "index.html"
ROOT_TEMPLATE_FILE = SCRIPT_DIR.parent / "assets" / "index.template.html"
ROOT_TEMPLATE = ROOT_TEMPLATE_FILE.read_text(encoding="utf-8") if ROOT_TEMPLATE_FILE.exists() else None

QUARTER_ORDER = [
    "2024Q1", "2024Q2", "2024Q3", "2024Q4",
    "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2",
]
ALL_STAGES = ["Technical Review", "Request for Service", "Contract for Electric Service"]
STAGE_COLORS = {
    "Technical Review": "#9bcce3",
    "Request for Service": "#529cba",
    "Contract for Electric Service": "#005d7f",
}
VINTAGE_COLORS = {
    "Technical Review":              ["#5da8ca", "#9bcce3", "#c8e4f2"],
    "Request for Service":           ["#2d6e8a", "#529cba", "#88c0d6"],
    "Contract for Electric Service": ["#003f58", "#005d7f", "#4091af"],
}
VINTAGE_LABELS = ["New (1 qtr)", "2-3 qtrs", "4+ qtrs"]
VINTAGE_IDX_TO_LABEL = {0: "4+ qtrs", 1: "2-3 qtrs", 2: "New (1 qtr)"}

METRIC_LABELS = {
    "load_change_dist": "Load Changes (count by long-term MW)",
    "projects_added_removed_count": "Projects added and removed (count)",
    "projects_added_removed_mw": "Projects added and removed (long-term MW)",
    "stage_changes_by_direction": "Stage changes (count) by direction",
    "schedule_delay_dist": "Schedule delay (months)",
    "pipeline_stage_flow": "Pipeline stage flow",
}

# Bins for the load change histogram (all quarters aggregated)
LOAD_CHANGE_BINS = [
    ("≤ -2000", -1e9, -2000), ("-1800 to -2000", -2000, -1800), ("-1600 to -1800", -1800, -1600),
    ("-1400 to -1600", -1600, -1400), ("-1200 to -1400", -1400, -1200), ("-1000 to -1200", -1200, -1000),
    ("-800 to -1000", -1000, -800), ("-600 to -800", -800, -600), ("-400 to -600", -600, -400),
    ("-200 to -400", -400, -200), ("-1 to -200", -200, 0), ("+1 to +200", 0, 200),
    ("+200 to +400", 200, 400), ("+400 to +600", 400, 600), ("+600 to +800", 600, 800),
    ("+800 to +1000", 800, 1000), ("+1000 to +1200", 1000, 1200), ("+1200 to +1400", 1200, 1400),
    ("+1400 to +1600", 1400, 1600), ("+1600 to +1800", 1600, 1800), ("+1800 to +2000", 1800, 2000),
    ("≥ +2000", 2000, 1e9),
]
# Simplified bins for the load change STACKED bar (per quarter) — 6 categories
LOAD_CHANGE_STACK_BINS = [
    ("Large decrease (≤ -500)", -1e9, -500, "#7f1d1d"),
    ("Moderate decrease (-200 to -500)", -500, -200, "#dc2626"),
    ("Small decrease (-1 to -200)", -200, 0, "#fca5a5"),
    ("Small increase (+1 to +200)", 0, 200, "#86efac"),
    ("Moderate increase (+200 to +500)", 200, 500, "#16a34a"),
    ("Large increase (≥ +500)", 500, 1e9, "#14532d"),
]
DELAY_BINS = [
    ("0 to 3", 0, 3), ("3 to 6", 3, 6), ("6 to 12", 6, 12),
    ("12 to 24", 12, 24), ("24+", 24, 1e9),
]


def vintage_bucket(age):
    if age == 1:
        return 2
    if age <= 3:
        return 1
    return 0


def parse_q_date(s):
    if not s or (isinstance(s, float) and pd.isna(s)) or pd.isna(s):
        return None
    m = re.match(r'Q\s*([1-4])\s*(\d{4})', str(s).strip())
    if not m:
        return None
    q, y = int(m.group(1)), int(m.group(2))
    return (y, (q - 1) * 3 + 1)


def q_diff_months(s1, s2):
    d1, d2 = parse_q_date(s1), parse_q_date(s2)
    if d1 is None or d2 is None:
        return None
    return (d2[0] - d1[0]) * 12 + (d2[1] - d1[1])


# ── Load combined CSVs ────────────────────────────────────────────────────────
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

QUARTERS_PRESENT_ALL = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique()]
QUARTERS_PRESENT = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique() and q != "2024Q1"]
ALL_YEARS = sorted(int(y) for y in df_long["planning_year"].unique())
ALL_SEGMENTS = sorted(s for s in df_long["segment"].dropna().unique().tolist() if s)

# ── Added / removed per project (for diverging bar) ───────────────────────────
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

for _df in (df_added, df_removed):
    if not _df.empty:
        _df["vintage_idx"] = _df["project_age"].apply(vintage_bucket)
        _df["vintage_label"] = _df["vintage_idx"].map(VINTAGE_IDX_TO_LABEL)

# ── Per-project QoQ events (load changes, stage transitions, schedule delays) ─
df_proj_sorted = df_proj.sort_values(["proj_id", "report_quarter"]).reset_index(drop=True)
load_change_events = []
stage_transition_events = []
schedule_delay_events = []

for _pid, _grp in df_proj_sorted.groupby("proj_id", sort=False):
    if len(_grp) < 2:
        continue
    _grp = _grp.reset_index(drop=True)
    for _i in range(1, len(_grp)):
        _prev = _grp.iloc[_i - 1]
        _curr = _grp.iloc[_i]
        _curr_q = _curr["report_quarter"]
        try:
            _prev_mw = float(_prev.get("announced_load_mw") or 0)
            _curr_mw = float(_curr.get("announced_load_mw") or 0)
        except (TypeError, ValueError):
            _prev_mw = _curr_mw = 0.0
        _change = _curr_mw - _prev_mw
        if _change != 0:
            load_change_events.append({
                "quarter": _curr_q,
                "proj_id": _pid,
                "change_mw": _change,
            })
        _ps, _cs = _prev.get("project_stage"), _curr.get("project_stage")
        if _ps and _cs and _ps != _cs and _ps != "Aggregate Total" and _cs != "Aggregate Total":
            stage_transition_events.append({
                "quarter": _curr_q,
                "proj_id": _pid,
                "from_stage": _ps,
                "to_stage": _cs,
            })
        _pd, _cd = _prev.get("initial_service_date"), _curr.get("initial_service_date")
        if _pd and _cd and str(_pd).strip() != str(_cd).strip():
            _delay = q_diff_months(_pd, _cd)
            if _delay is not None:
                schedule_delay_events.append({
                    "quarter": _curr_q,
                    "proj_id": _pid,
                    "delay_months": _delay,
                })

# ── Diverging bar data: added/removed by (stage, vintage) ─────────────────────
diverging_rows = []
for _df, _direction in ((df_added, "added"), (df_removed, "removed")):
    if _df.empty:
        continue
    for _, _r in _df.iterrows():
        diverging_rows.append({
            "quarter": _r["report_quarter"],
            "direction": _direction,
            "stage": _r["project_stage"],
            "vintage": _r.get("vintage_label", "New (1 qtr)"),
            "count": 1,
            "mw": float(_r.get("announced_load_mw") or 0),
        })

# ── Stage changes by direction (count per transition per quarter) ─────────────
_sbd_df = (
    pd.DataFrame(stage_transition_events)
    .groupby(["quarter", "from_stage", "to_stage"], as_index=False)
    .size()
    .rename(columns={"size": "count"})
    if stage_transition_events
    else pd.DataFrame(columns=["quarter", "from_stage", "to_stage", "count"])
)

# ── Sankey flows per quarter (compare prev quarter → current quarter) ─────────
sankey_rows = []
for _i in range(1, len(QUARTERS_PRESENT_ALL)):
    _prev_q = QUARTERS_PRESENT_ALL[_i - 1]
    _curr_q = QUARTERS_PRESENT_ALL[_i]
    _prev_df = df_proj[df_proj["report_quarter"] == _prev_q].set_index("proj_id")
    _curr_df = df_proj[df_proj["report_quarter"] == _curr_q].set_index("proj_id")
    _prev_ids = set(_prev_df.index)
    _curr_ids = set(_curr_df.index)
    _flows = {}
    for _pid in _prev_ids & _curr_ids:
        _src = _prev_df.loc[_pid, "project_stage"]
        _tgt = _curr_df.loc[_pid, "project_stage"]
        if _src and _tgt and _src != "Aggregate Total" and _tgt != "Aggregate Total":
            _flows[(_src, _tgt)] = _flows.get((_src, _tgt), 0) + 1
    for _pid in _curr_ids - _prev_ids:
        _tgt = _curr_df.loc[_pid, "project_stage"]
        if _tgt and _tgt != "Aggregate Total":
            _flows[("New", _tgt)] = _flows.get(("New", _tgt), 0) + 1
    for _pid in _prev_ids - _curr_ids:
        _src = _prev_df.loc[_pid, "project_stage"]
        if _src and _src != "Aggregate Total":
            _flows[(_src, "Removed")] = _flows.get((_src, "Removed"), 0) + 1
    for (_src, _tgt), _v in _flows.items():
        sankey_rows.append({
            "quarter": _curr_q,
            "source": _src,
            "target": _tgt,
            "value": _v,
        })

# ── Aggregated Sankey flows (sum across all QoQ pairs) ────────────────────────
_sankey_agg = {}
for _f in sankey_rows:
    _k = _f["source"] + "|" + _f["target"]
    _sankey_agg[_k] = _sankey_agg.get(_k, 0) + _f["value"]
sankey_aggregated = [
    {"source": k.split("|", 1)[0], "target": k.split("|", 1)[1], "value": v}
    for k, v in _sankey_agg.items()
]

# ── Unique stage change directions (sorted, used for stacked bar legend) ──────
stage_change_directions = sorted({
    f"{t['from_stage']} \u2192 {t['to_stage']}"
    for t in stage_transition_events
})

# ── Exploded-grid Sankey (stages × quarters, plus per-quarter New/Removed) ───
# ---------------------------------------------------------------------------
# Quarter ramp for the Pipeline Evolution tab.
#
# The old ramp interpolated sRGB from RMI teal to RMI navy. Both endpoints are
# blue-ish, so nine quarters compressed into a worst adjacent OKLab dE of 4.9 --
# well under the dE 15 at which neighbouring series read as distinct -- and the
# lightest step sat at 1.99:1 contrast, effectively invisible on the #fafafa
# plot area.
#
# A single-hue ramp cannot fix this: holding the lightest step at the 2:1
# contrast floor caps lightness near L=0.74, and 9 steps down from there give
# dL ~= 0.055 per step, i.e. dE ~= 5.5. Hue is the only channel with headroom,
# so this ramp keeps lightness monotone (so the reader still sees quarter order)
# and spends 240 degrees of hue on separation. Chroma is clamped into sRGB per
# step, because saturated cyan does not exist at mid lightness.
#
# Measured at 9 quarters: worst adjacent AND worst all-pairs dE 8.7 (was 4.9),
# dL 0.058, min chroma 0.104, lightest-step contrast 2.04. All pairs equal
# adjacent pairs, which confirms the hue path never folds back on itself.
RAMP_L = (0.74, 0.26)      # oldest -> newest; newest stays darkest, as before
RAMP_H = (150.0, 390.0)    # green -> teal -> blue -> purple -> magenta -> maroon
RAMP_C = 0.19              # requested chroma, clamped per step


def _oklch_to_linear(L, C, H):
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, sv = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * sv,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * sv,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * sv)


def _in_gamut(L, C, H):
    return all(-1e-6 <= v <= 1 + 1e-6 for v in _oklch_to_linear(L, C, H))


def _oklch_to_hex(L, C, H):
    def enc(v):
        v = max(0.0, min(1.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
        return max(0, min(255, round(v * 255)))
    return "#" + "".join(f"{enc(v):02x}" for v in _oklch_to_linear(L, C, H))


def quarter_ramp(n):
    """n evenly spaced steps along the ramp, darkest (newest) last."""
    if n <= 0:
        return []
    if n == 1:
        return [_oklch_to_hex(RAMP_L[1], min(RAMP_C, 0.12), RAMP_H[1])]
    out = []
    for i in range(n):
        t = i / (n - 1)
        L = RAMP_L[0] + (RAMP_L[1] - RAMP_L[0]) * t
        H = RAMP_H[0] + (RAMP_H[1] - RAMP_H[0]) * t
        c = RAMP_C
        if not _in_gamut(L, c, H):            # bisect to the gamut boundary
            lo, hi = 0.0, c
            for _ in range(20):
                mid = (lo + hi) / 2
                if _in_gamut(L, mid, H):
                    lo = mid
                else:
                    hi = mid
            c = lo
        out.append(_oklch_to_hex(L, c, H))
    return out


QUARTER_COLORS = dict(zip(QUARTERS_PRESENT, quarter_ramp(len(QUARTERS_PRESENT))))


def _quarter_label(q):
    """'2026Q2' -> 'Q2 2026' for display."""
    return f"{q[4:]} {q[:4]}"


# Chart titles used to hardcode this range, so every new quarter needed a manual
# template edit. Derive it instead.
QUARTER_RANGE_LABEL = (
    f"{_quarter_label(QUARTERS_PRESENT_ALL[0])} – {_quarter_label(QUARTERS_PRESENT_ALL[-1])}"
    if QUARTERS_PRESENT_ALL else ""
)

_QUARTERS_EXP = QUARTERS_PRESENT_ALL  # all quarters, including the 2024Q1 seed
_FIRST_Q = _QUARTERS_EXP[0]
_LAST_Q = _QUARTERS_EXP[-1]
_STAGE_ORDER = ALL_STAGES
_ROW_Y = {
    "New": 0.0,
    "Technical Review": 0.25,
    "Request for Service": 0.5,
    "Contract for Electric Service": 0.75,
    "Removed": 1.0,
}
_HIDDEN_COLOR = "rgba(0,0,0,0)"
_HIDDEN_NODES = {"_source", "_still_in_pipeline"}


def _stage_key(stage, quarter):
    return f"{stage}|{quarter}"


_grid_nodes = []
_grid_node_idx = {}
_grid_flows = {}  # (source_id, target_id) -> count


def _add_node(nid, label, x, y, color):
    if nid in _grid_node_idx:
        return
    _grid_node_idx[nid] = len(_grid_nodes)
    _grid_nodes.append({
        "id": nid,
        "label": label,
        "x": x, "y": y,
        "color": color,
    })


# Add "New Qx" and "Removed Qx" for each quarter (rows y=0 and y=1)
_n = max(len(_QUARTERS_EXP) - 1, 1)
for _i, _q in enumerate(_QUARTERS_EXP):
    _x = _i / _n
    _add_node(_stage_key("New", _q), "New", _x, _ROW_Y["New"], "#9ca3af")
    _add_node(_stage_key("Removed", _q), "Removed", _x, _ROW_Y["Removed"], "#374151")

# Add (Stage, Qx) for each stage and quarter
for _i, _q in enumerate(_QUARTERS_EXP):
    _x = _i / _n
    for _stage in _STAGE_ORDER:
        _add_node(_stage_key(_stage, _q), _stage, _x, _ROW_Y[_stage], STAGE_COLORS[_stage])

# Balance the seed column: each (Stage, first quarter) needs inflow from a hidden
# _source equal to the count of projects in that stage (so outflow = inflow).
_q1_stage_counts = (
    df_proj[df_proj["report_quarter"] == _FIRST_Q]["project_stage"]
    .value_counts()
    .to_dict()
)
_q1_removed_count = int(df_changes[df_changes["report_quarter"] == _FIRST_Q]["removed_projects"].fillna(0).sum())
if any(_q1_stage_counts.get(_s, 0) > 0 for _s in _STAGE_ORDER) or _q1_removed_count > 0:
    _add_node("_source", "", -0.04, 0.5, _HIDDEN_COLOR)
    for _stage in _STAGE_ORDER:
        _cnt = int(_q1_stage_counts.get(_stage, 0))
        if _cnt > 0:
            _tgt = _stage_key(_stage, _FIRST_Q)
            _grid_flows[("_source", _tgt)] = _grid_flows.get(("_source", _tgt), 0) + _cnt
    if _q1_removed_count > 0:
        _tgt = _stage_key("Removed", _FIRST_Q)
        _grid_flows[("_source", _tgt)] = _grid_flows.get(("_source", _tgt), 0) + _q1_removed_count

# For each consecutive pair (Q-1, Q): stays, transitions, new entries, removals
for _i in range(1, len(_QUARTERS_EXP)):
    _prev_q = _QUARTERS_EXP[_i - 1]
    _curr_q = _QUARTERS_EXP[_i]
    _prev_df = df_proj[df_proj["report_quarter"] == _prev_q].set_index("proj_id")
    _curr_df = df_proj[df_proj["report_quarter"] == _curr_q].set_index("proj_id")
    _prev_ids = set(_prev_df.index)
    _curr_ids = set(_curr_df.index)

    for _pid in _prev_ids & _curr_ids:
        _ps = _prev_df.loc[_pid, "project_stage"]
        _cs = _curr_df.loc[_pid, "project_stage"]
        if _ps not in _STAGE_ORDER or _cs not in _STAGE_ORDER:
            continue
        _src = _stage_key(_ps, _prev_q)
        _tgt = _stage_key(_cs, _curr_q)
        _grid_flows[(_src, _tgt)] = _grid_flows.get((_src, _tgt), 0) + 1

    for _pid in _curr_ids - _prev_ids:
        _cs = _curr_df.loc[_pid, "project_stage"]
        if _cs not in _STAGE_ORDER:
            continue
        _src = _stage_key("New", _curr_q)
        _tgt = _stage_key(_cs, _curr_q)
        _grid_flows[(_src, _tgt)] = _grid_flows.get((_src, _tgt), 0) + 1

    for _pid in _prev_ids - _curr_ids:
        _ps = _prev_df.loc[_pid, "project_stage"]
        if _ps not in _STAGE_ORDER:
            continue
        _src = _stage_key(_ps, _prev_q)
        _tgt = _stage_key("Removed", _curr_q)
        _grid_flows[(_src, _tgt)] = _grid_flows.get((_src, _tgt), 0) + 1

# Balance the final column: each (Stage, last quarter) needs outflow to
# _still_in_pipeline equal to its total inflow.
_q_last_in = {stage: 0 for stage in _STAGE_ORDER}
for (_src, _tgt), _cnt in _grid_flows.items():
    for _stage in _STAGE_ORDER:
        if _tgt == _stage_key(_stage, _LAST_Q):
            _q_last_in[_stage] += _cnt
            break
if any(_v > 0 for _v in _q_last_in.values()):
    _add_node("_still_in_pipeline", "", 1.04, 0.5, _HIDDEN_COLOR)
    for _stage in _STAGE_ORDER:
        if _q_last_in[_stage] > 0:
            _src = _stage_key(_stage, _LAST_Q)
            _grid_flows[(_src, "_still_in_pipeline")] = (
                _grid_flows.get((_src, "_still_in_pipeline"), 0) + _q_last_in[_stage]
            )

# Convert flows to list, marking hidden ones (involving _source or _still_in_pipeline)
_grid_links = []
for (_src, _tgt), _cnt in sorted(_grid_flows.items()):
    if _cnt <= 0:
        continue
    _grid_links.append({
        "source": _src,
        "target": _tgt,
        "value": _cnt,
    })

sankey_grid = {
    "nodes": _grid_nodes,
    "links": _grid_links,
    "hidden_node_ids": sorted(_HIDDEN_NODES),
}


# ── Load GPC load forecasts for reference line overlays ──────────────────────
df_fc = pd.read_csv(INPUTS_DIR / "GPC_Load_Forecasts.csv")
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
    "qoq_events": {
        "load_changes": load_change_events,
        "stage_transitions": stage_transition_events,
        "schedule_delays": schedule_delay_events,
    },
    "diverging": diverging_rows,
    "stage_by_direction": _sbd_df.to_dict("records"),
    "sankey_grid": sankey_grid,
    "stage_change_directions": stage_change_directions,
    "meta": {
        "quarters": QUARTERS_PRESENT,
        "quarters_all": QUARTERS_PRESENT_ALL,
        "quarter_range": QUARTER_RANGE_LABEL,
        "quarter_colors": QUARTER_COLORS,
        "years": ALL_YEARS,
        "segments": ALL_SEGMENTS,
        "stages": ALL_STAGES,
        "vintage_labels": VINTAGE_LABELS,
        "stage_colors": STAGE_COLORS,
        "vintage_colors": VINTAGE_COLORS,
        "metric_labels": METRIC_LABELS,
        "forecast_labels": {f["id"]: f["title"] for f in forecast_data},
        "load_change_bins": [{"label": b[0], "lo": b[1], "hi": b[2]} for b in LOAD_CHANGE_BINS],
        "load_change_stack_bins": [{"label": b[0], "lo": b[1], "hi": b[2], "color": b[3]} for b in LOAD_CHANGE_STACK_BINS],
        "delay_bins": [{"label": b[0], "lo": b[1], "hi": b[2]} for b in DELAY_BINS],
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
    print(f"  QoQ events: load_changes={len(EMBEDDED['qoq_events']['load_changes'])}, "
          f"stage_transitions={len(EMBEDDED['qoq_events']['stage_transitions'])}, "
          f"schedule_delays={len(EMBEDDED['qoq_events']['schedule_delays'])}")
    print(f"  Diverging rows: {len(EMBEDDED['diverging'])}, "
          f"Stage-by-direction: {len(EMBEDDED['stage_by_direction'])}, "
          f"Sankey grid: {len(EMBEDDED['sankey_grid']['nodes'])} nodes, {len(EMBEDDED['sankey_grid']['links'])} links")
    print(f"  Stage change directions: {len(EMBEDDED['stage_change_directions'])}")
    print(f"  Forecasts: {len(EMBEDDED['forecasts'])}, Quarters: {len(EMBEDDED['meta']['quarters'])}, Years: {len(EMBEDDED['meta']['years'])}")


if __name__ == "__main__":
    main()
