"""
Generates a self-contained static HTML page with Plotly.js charts
for the Georgia Power Large Load Economic Development Pipeline.
Embeds all data as JSON — no server needed.
Output: large-loads-reports/output/index.html
"""
import json
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).parent
COMBINED_DIR = SCRIPT_DIR.parent / "outputs" / "combined"
OUTPUT_DIR = SCRIPT_DIR.parent / "output"
OUT = OUTPUT_DIR / "index.html"
ROOT = SCRIPT_DIR.parent / "index.html"

df_proj = pd.read_csv(COMBINED_DIR / "pipeline_projects.csv")
df_changes = pd.read_csv(COMBINED_DIR / "pipeline_changes.csv")

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
QUARTERS_PRESENT = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique()]
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
for i in range(1, len(QUARTERS_PRESENT)):
    prev_q = QUARTERS_PRESENT[i - 1]
    curr_q = QUARTERS_PRESENT[i]
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
    "meta": {
        "quarters": QUARTERS_PRESENT,
        "years": ALL_YEARS,
        "segments": ALL_SEGMENTS,
        "stages": ALL_STAGES,
        "vintage_labels": VINTAGE_LABELS,
        "stage_colors": STAGE_COLORS,
        "vintage_colors": VINTAGE_COLORS,
        "metric_labels": METRIC_LABELS,
    },
}

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GA Power Large Load Pipeline</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f5f6fa;
    --surface: #ffffff;
    --border: #e2e6ea;
    --text: #1a2332;
    --muted: #6b7a8d;
    --accent: #1d4ed8;
    --tab-active: #1a1a2e;
  }
  html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }

  /* Header */
  header {
    background: var(--surface);
    border-bottom: 2px solid #e8e8e8;
    padding: 20px 30px 16px;
  }
  header h1 { font-size: 22px; font-weight: 700; color: #1a1a2e; margin: 0; }
  header p { margin: 4px 0 0; color: #666; font-size: 13px; }

  /* Tabs */
  .tab-bar {
    display: flex;
    gap: 4px;
    background: var(--surface);
    padding: 0 30px;
    border-bottom: 1px solid var(--border);
  }
  .tab-btn {
    padding: 12px 18px;
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    transition: color .15s, border-color .15s;
  }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--tab-active); border-bottom-color: var(--tab-active); }

  /* Content */
  .tab-content { display: none; padding: 24px 30px; }
  .tab-content.active { display: block; }

  /* Cards */
  .card {
    background: var(--surface);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    margin-bottom: 20px;
  }

  /* Controls */
  .controls-row { display: flex; gap: 24px; flex-wrap: wrap; }
  .control-group { min-width: 180px; }
  .control-label { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: #444; }
  .control-group label { display: block; font-size: 13px; margin-bottom: 3px; cursor: pointer; }
  .control-group select, .control-group input[type="text"] {
    width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px;
  }
  .toggle-links { font-size: 11px; margin-bottom: 6px; }
  .toggle-links span { cursor: pointer; color: #5B8DB8; margin-right: 8px; }
  .toggle-links span:hover { text-decoration: underline; }

  /* Range slider */
  .range-wrap { display: flex; align-items: center; gap: 10px; }
  .range-wrap input[type="range"] { flex: 1; }
  .range-wrap .range-label { font-size: 12px; color: var(--muted); min-width: 30px; text-align: center; }

  /* Radio */
  .radio-group label { display: inline-block; margin-right: 20px; margin-bottom: 4px; }

  /* Chart area */
  .chart-area { display: flex; gap: 20px; }
  .chart-sidebar { width: 240px; flex-shrink: 0; }
  .chart-main { flex: 1; min-width: 0; }
  .chart-subtitle { font-size: 14px; color: #555; margin-bottom: 12px; }

  /* Table */
  .table-wrap { overflow-x: auto; }
  table.data-table {
    width: 100%; border-collapse: collapse; font-size: 12px;
  }
  table.data-table th {
    background: #f0f2f5; font-weight: bold; padding: 8px 12px;
    text-align: left; border-bottom: 2px solid var(--border); cursor: pointer; white-space: nowrap;
  }
  table.data-table th:hover { background: #e4e7ec; }
  table.data-table td { padding: 6px 12px; border-bottom: 1px solid var(--border); }
  table.data-table tr:hover { background: #f8f9fb; }
  table.data-table .num { text-align: right; }

  /* Responsive */
  @media (max-width: 768px) {
    .chart-area { flex-direction: column; }
    .chart-sidebar { width: 100%; }
    .tab-content { padding: 16px; }
  }
</style>
</head>
<body>

<header>
  <h1>Georgia Power Large Load Economic Development Pipeline</h1>
  <p>Docket 55378 &middot; Quarterly Reports Q1 2024 &ndash; Q1 2026</p>
</header>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="snapshot">Pipeline Snapshot</button>
  <button class="tab-btn" data-tab="evolution">Pipeline Evolution</button>
  <button class="tab-btn" data-tab="changes">Quarter-over-Quarter Changes</button>
  <button class="tab-btn" data-tab="vintage">Snapshot by Vintage</button>
</div>

<!-- Tab 1: Snapshot -->
<div class="tab-content active" id="tab-snapshot">
  <div class="chart-area">
    <div class="chart-sidebar">
      <div class="card">
        <div class="control-group">
          <div class="control-label">Report Quarter</div>
          <select id="snap-quarter"></select>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Pipeline Stages</div>
          <div id="snap-stages"></div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Segments</div>
          <div class="toggle-links"><span id="snap-seg-all">All</span><span id="snap-seg-none">None</span></div>
          <div id="snap-segments"></div>
        </div>
      </div>
    </div>
    <div class="chart-main">
      <div class="chart-subtitle" id="snap-subtitle"></div>
      <div class="card"><div id="snap-chart"></div></div>
      <div class="card">
        <div class="control-label" style="margin-bottom:8px">Projects in selected quarter</div>
        <div class="table-wrap" id="snap-table-wrap"></div>
      </div>
    </div>
  </div>
</div>

<!-- Tab 2: Evolution -->
<div class="tab-content" id="tab-evolution">
  <div class="chart-area">
    <div class="chart-sidebar">
      <div class="card">
        <div class="control-group">
          <div class="control-label">Report Quarters</div>
          <div class="toggle-links"><span id="evo-all">All</span><span id="evo-none">None</span></div>
          <div id="evo-quarters"></div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Pipeline Stages</div>
          <div id="evo-stages"></div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Planning Years</div>
          <div class="range-wrap">
            <span class="range-label" id="evo-year-min"></span>
            <input type="range" id="evo-year-lo" min="" max="">
            <input type="range" id="evo-year-hi" min="" max="">
            <span class="range-label" id="evo-year-max"></span>
          </div>
          <div style="text-align:center;font-size:12px;color:var(--muted);margin-top:4px">
            <span id="evo-year-lo-val"></span> &ndash; <span id="evo-year-hi-val"></span>
          </div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Show stages</div>
          <div class="radio-group">
            <label><input type="radio" name="evo-agg" value="sum" checked> Combined (sum all selected)</label>
            <label><input type="radio" name="evo-agg" value="each"> Separate lines per stage</label>
          </div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Segments</div>
          <div class="toggle-links"><span id="evo-seg-all">All</span><span id="evo-seg-none">None</span></div>
          <div id="evo-segments"></div>
        </div>
      </div>
    </div>
    <div class="chart-main">
      <div class="card"><div id="evo-chart"></div></div>
    </div>
  </div>
</div>

<!-- Tab 3: Changes -->
<div class="tab-content" id="tab-changes">
  <div class="card">
    <div class="control-label">Aggregate Metric</div>
    <div class="radio-group" id="chg-metrics"></div>
  </div>
  <div class="card"><div id="chg-chart"></div></div>
  <div class="card">
    <div class="control-label" style="margin-bottom:8px">Full quarterly change summary</div>
    <div class="table-wrap" id="chg-table-wrap"></div>
  </div>
</div>

<!-- Tab 4: Vintage -->
<div class="tab-content" id="tab-vintage">
  <div class="chart-area">
    <div class="chart-sidebar">
      <div class="card">
        <div class="control-group">
          <div class="control-label">Report Quarter</div>
          <select id="vint-quarter"></select>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Pipeline Stages</div>
          <div id="vint-stages"></div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Vintage</div>
          <div class="toggle-links"><span id="vint-vint-all">All</span><span id="vint-vint-none">None</span></div>
          <div id="vint-vintages"></div>
        </div>
        <div style="margin-top:12px">
          <div class="control-label">Segments</div>
          <div class="toggle-links"><span id="vint-seg-all">All</span><span id="vint-seg-none">None</span></div>
          <div id="vint-segments"></div>
        </div>
      </div>
    </div>
    <div class="chart-main">
      <div class="chart-subtitle" id="vint-subtitle"></div>
      <div class="card"><div id="vint-chart"></div></div>
    </div>
  </div>
</div>

<script>
// ── Embedded data ────────────────────────────────────────────────────────────
const DATA = __DATA_PLACEHOLDER__;
const META = DATA.meta;
const D = DATA.long;
const CHANGES = DATA.changes;
const TABLE = DATA.table;
const ADDED = DATA.added;
const REMOVED = DATA.removed;

// ── Helpers ──────────────────────────────────────────────────────────────────
const QUARTERS = META.quarters;
const STAGES = META.stages;
const SEGMENTS = META.segments;
const YEARS = META.years;
const VINTAGE_LABELS = META.vintage_labels;
const STAGE_COLORS = META.stage_colors;
const VINTAGE_COLORS = META.vintage_colors;
const METRIC_LABELS = META.metric_labels;

function vintIdx(label) { return VINTAGE_LABELS.indexOf(label); }
function vintBucket(age) { return age === 1 ? 2 : age <= 3 ? 1 : 0; }

// ── Checkbox builder ─────────────────────────────────────────────────────────
function buildCheckboxes(containerId, items, values, onChange) {
  const c = document.getElementById(containerId);
  c.innerHTML = items.map(v =>
    `<label><input type="checkbox" value="${v}" ${values.includes(v) ? 'checked' : ''}> ${v}</label>`
  ).join('');
  c.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', onChange);
  });
}

function buildSelect(selId, items, onChange) {
  const sel = document.getElementById(selId);
  sel.innerHTML = items.map(v => `<option value="${v}">${v}</option>`).join('');
  sel.addEventListener('change', onChange);
}

function getChecked(containerId) {
  return Array.from(document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`)).map(cb => cb.value);
}

function setAll(containerId, checked) {
  document.querySelectorAll(`#${containerId} input[type="checkbox"]`).forEach(cb => cb.checked = checked);
}

function escHtml(s) {
  if (s == null) return '&mdash;';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmt(n) {
  if (n == null || isNaN(n)) return '&mdash;';
  return Number(n).toLocaleString();
}

// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
  if (tab === 'snapshot') renderSnapshot();
  if (tab === 'evolution') renderEvolution();
  if (tab === 'changes') renderChanges();
  if (tab === 'vintage') renderVintage();
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Render: Snapshot ─────────────────────────────────────────────────────────
function renderSnapshot() {
  const quarter = document.getElementById('snap-quarter').value;
  const stages = getChecked('snap-stages');
  const segments = getChecked('snap-segments');
  if (!stages.length || !segments.length) {
    document.getElementById('snap-subtitle').textContent = '';
    Plotly.react('snap-chart', [], {});
    buildTable('snap-table-wrap', [], ['proj_id','project_stage','segment','territory','announced_load_mw','initial_service_date','project_age','match_confidence']);
    return;
  }

  const filtered = D.filter(r => r.report_quarter === quarter && stages.includes(r.project_stage) && segments.includes(r.segment));

  const grouped = {};
  filtered.forEach(r => {
    const key = r.planning_year;
    if (!grouped[key]) grouped[key] = {};
    if (!grouped[key][r.project_stage]) grouped[key][r.project_stage] = 0;
    grouped[key][r.project_stage] += r.load_mw;
  });

  const years = [...new Set(filtered.map(r => r.planning_year))].sort((a,b) => a-b);

  const traces = STAGES.filter(s => stages.includes(s)).reverse().map(stage => ({
    x: years,
    y: years.map(y => grouped[y] && grouped[y][stage] ? grouped[y][stage] : 0),
    name: stage,
    type: 'bar',
    marker: { color: STAGE_COLORS[stage] },
    hovertemplate: `<b>%{x}</b><br>${stage}: %{y:,.0f} MW<extra></extra>`,
  }));

  const layout = {
    barmode: 'stack',
    xaxis: { title: 'Planning Year', tickmode: 'linear', dtick: 1 },
    yaxis: { title: 'Total Pipeline MW', tickformat: ',' },
    legend: { orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1 },
    plot_bgcolor: '#fafafa', paper_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 60, r: 20, t: 40, b: 60 }, hovermode: 'x unified',
    height: 520,
  };

  const totalMw = {};
  filtered.forEach(r => { totalMw[r.planning_year] = (totalMw[r.planning_year] || 0) + r.load_mw; });
  const peakEntries = Object.entries(totalMw).sort((a,b) => b[1] - a[1]);
  const peakYr = peakEntries.length ? peakEntries[0][0] : '&mdash;';
  const peakMw = peakEntries.length ? Number(peakEntries[0][1]).toLocaleString() : '&mdash;';
  document.getElementById('snap-subtitle').textContent = `${quarter} snapshot · Peak planning year: ${peakYr} at ${peakMw} MW total`;

  Plotly.react('snap-chart', traces, layout);

  // Project table
  const projCols = ['proj_id','project_stage','segment','territory','announced_load_mw','initial_service_date','project_age','match_confidence'];
  const projRows = TABLE.filter(r => r.report_quarter === quarter && stages.includes(r.project_stage) && segments.includes(r.segment));
  buildTable('snap-table-wrap', projRows, projCols);
}

// ── Render: Evolution ────────────────────────────────────────────────────────
const QUARTER_COLORS = {};
const PALETTE = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'];
QUARTERS.forEach((q,i) => { QUARTER_COLORS[q] = PALETTE[i % PALETTE.length]; });

function renderEvolution() {
  const quarters = getChecked('evo-quarters');
  const stages = getChecked('evo-stages');
  const segments = getChecked('evo-segments');
  const agg = document.querySelector('input[name="evo-agg"]:checked').value;
  const yrLo = parseInt(document.getElementById('evo-year-lo').value);
  const yrHi = parseInt(document.getElementById('evo-year-hi').value);

  if (!stages.length || !quarters.length || !segments.length) {
    Plotly.react('evo-chart', [], {});
    return;
  }

  const filtered = D.filter(r =>
    quarters.includes(r.report_quarter) &&
    stages.includes(r.project_stage) &&
    segments.includes(r.segment) &&
    r.planning_year >= yrLo && r.planning_year <= yrHi
  );

  const quartersSorted = QUARTERS.filter(q => quarters.includes(q));
  const years = [];
  for (let y = yrLo; y <= yrHi; y++) years.push(y);

  const traces = [];

  if (agg === 'sum') {
    const grouped = {};
    filtered.forEach(r => {
      const k = r.report_quarter + '|' + r.planning_year;
      grouped[k] = (grouped[k] || 0) + r.load_mw;
    });
    quartersSorted.forEach(q => {
      const yVals = years.map(y => grouped[q + '|' + y] || 0);
      traces.push({
        x: years, y: yVals, mode: 'lines+markers', name: q,
        line: { color: QUARTER_COLORS[q], width: 2.5 },
        marker: { size: 7 },
        hovertemplate: `<b>%{x}</b><br>${q}: %{y:,.0f} MW<extra></extra>`,
      });
    });
  } else {
    const grouped = {};
    filtered.forEach(r => {
      const k = r.report_quarter + '|' + r.project_stage + '|' + r.planning_year;
      grouped[k] = (grouped[k] || 0) + r.load_mw;
    });
    const dashes = ['solid', 'dash', 'dot'];
    quartersSorted.forEach((q, qi) => {
      STAGES.forEach((stage, si) => {
        if (!stages.includes(stage)) return;
        const yVals = years.map(y => grouped[q + '|' + stage + '|' + y] || 0);
        if (yVals.every(v => v === 0)) return;
        traces.push({
          x: years, y: yVals, mode: 'lines+markers',
          name: `${q} · ${stage}`,
          line: { color: QUARTER_COLORS[q], width: 1.8, dash: dashes[si % dashes.length] },
          marker: { size: 5 },
          hovertemplate: `<b>%{x}</b><br>${q} ${stage}: %{y:,.0f} MW<extra></extra>`,
        });
      });
    });
  }

  const stageLabel = stages.length === 3 ? 'all stages' : stages.join(' + ');
  const ylabel = agg === 'sum' ? `Total Pipeline MW (${stageLabel})` : 'Pipeline MW by Stage';

  const layout = {
    xaxis: { title: 'Planning Year', tickmode: 'linear', dtick: 1 },
    yaxis: { title: ylabel, tickformat: ',' },
    legend: { orientation: 'v', x: 1.01, y: 1, font: { size: 11 } },
    plot_bgcolor: '#fafafa', paper_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 60, r: 200, t: 20, b: 60 }, hovermode: 'x unified',
    height: 540,
  };

  Plotly.react('evo-chart', traces, layout);
}

// ── Render: Changes ──────────────────────────────────────────────────────────
function renderChanges() {
  const metric = document.querySelector('input[name="chg-metric"]:checked').value;
  const flowMetrics = ['added_projects','added_mw','removed_projects','removed_mw'];
  const qs = QUARTERS.filter(q => q !== '2024Q1');

  if (flowMetrics.includes(metric)) {
    const df = metric.startsWith('added') ? ADDED : REMOVED;
    const view = metric.endsWith('_mw') ? 'mw' : 'count';
    const unit = view === 'mw' ? 'MW' : 'projects';
    const ylabel = view === 'mw' ? 'Announced MW' : 'Project Count';
    const flowTitle = metric.startsWith('added') ? 'Projects Added' : 'Projects Removed';

    const traces = [];
    STAGES.slice().reverse().forEach(stage => {
      const colors = VINTAGE_COLORS[stage];
      VINTAGE_LABELS.forEach((vlabel, vidx) => {
        const mask = df.filter(r =>
          qs.includes(r.report_quarter) &&
          r.project_stage === stage &&
          r.vintage_label === vlabel
        );
        if (!mask.length) return;

        const vals = qs.map(q => {
          const items = mask.filter(r => r.report_quarter === q);
          if (view === 'mw') return items.reduce((s, r) => s + (r.announced_load_mw || 0), 0);
          return items.length;
        });
        if (vals.every(v => v === 0)) return;

        traces.push({
          x: qs, y: vals, type: 'bar',
          name: `${stage.slice(0,3)}\u2026 \u00b7 ${vlabel}`,
          marker: { color: colors[vidx] },
          legendgroup: stage,
          legendgrouptitle: { text: stage },
          hovertemplate: `<b>%{x}</b><br>${stage}<br>${vlabel}: %{y:,.0f} ${unit}<extra></extra>`,
        });
      });
    });

    const layout = {
      barmode: 'stack',
      xaxis: { title: 'Report Quarter' },
      yaxis: { title: ylabel, tickformat: ',' },
      legend: { groupclick: 'toggleitem', orientation: 'v', x: 1.01, y: 1, font: { size: 11 } },
      plot_bgcolor: '#fafafa', paper_bgcolor: 'rgba(0,0,0,0)',
      margin: { l: 60, r: 200, t: 20, b: 50 },
      height: 420,
    };
    Plotly.react('chg-chart', traces, layout);
  } else {
    const sub = CHANGES.filter(r => r[metric] != null).sort((a,b) => QUARTERS.indexOf(a.report_quarter) - QUARTERS.indexOf(b.report_quarter));
    const colors = sub.map(r => r[metric] < 0 ? '#c62828' : r[metric] > 0 ? '#2e7d32' : '#999');
    const trace = {
      x: sub.map(r => r.report_quarter), y: sub.map(r => r[metric]),
      type: 'bar', marker: { color: colors },
      hovertemplate: `<b>%{x}</b><br>${METRIC_LABELS[metric]}: %{y:,.1f}<extra></extra>`,
    };
    const layout = {
      xaxis: { title: 'Report Quarter' },
      yaxis: { title: METRIC_LABELS[metric], tickformat: ',' },
      shapes: [{
        type: 'line', x0: -0.5, x1: sub.length - 0.5, y0: 0, y1: 0,
        line: { color: '#888', width: 1 },
      }],
      plot_bgcolor: '#fafafa', paper_bgcolor: 'rgba(0,0,0,0)',
      margin: { l: 60, r: 20, t: 20, b: 50 },
      height: 420,
    };
    Plotly.react('chg-chart', [trace], layout);
  }
}

// ── Render: Vintage ──────────────────────────────────────────────────────────
function renderVintage() {
  const quarter = document.getElementById('vint-quarter').value;
  const stages = getChecked('vint-stages');
  const vintages = getChecked('vint-vintages');
  const segments = getChecked('vint-segments');
  if (!stages.length || !segments.length || !vintages.length) {
    document.getElementById('vint-subtitle').textContent = '';
    Plotly.react('vint-chart', [], {});
    return;
  }

  const filtered = D.filter(r =>
    r.report_quarter === quarter &&
    stages.includes(r.project_stage) &&
    segments.includes(r.segment)
  ).map(r => {
    const vi = vintBucket(r.project_age);
    return { ...r, vintage_idx: vi, vintage_label: VINTAGE_LABELS[vi] };
  }).filter(r => vintages.includes(r.vintage_label));

  const traces = [];
  STAGES.slice().reverse().forEach(stage => {
    if (!stages.includes(stage)) return;
    const colors = VINTAGE_COLORS[stage];
    VINTAGE_LABELS.forEach((vlabel, vidx) => {
      if (!vintages.includes(vlabel)) return;
      const sub = filtered.filter(r => r.project_stage === stage && r.vintage_label === vlabel);
      if (!sub.length) return;
      const years = [...new Set(sub.map(r => r.planning_year))].sort((a,b) => a-b);
      const grouped = {};
      sub.forEach(r => { grouped[r.planning_year] = (grouped[r.planning_year] || 0) + r.load_mw; });
      const yVals = years.map(y => grouped[y] || 0);
      if (yVals.every(v => v === 0)) return;

      traces.push({
        x: years, y: yVals, type: 'bar',
        name: `${stage.slice(0,3)}\u2026 \u00b7 ${vlabel}`,
        marker: { color: colors[vidx] },
        legendgroup: stage,
        legendgrouptitle: { text: stage },
        hovertemplate: `<b>%{x}</b><br>${stage}<br>${vlabel}: %{y:,.0f} MW<extra></extra>`,
      });
    });
  });

  const totalMw = {};
  filtered.forEach(r => { totalMw[r.planning_year] = (totalMw[r.planning_year] || 0) + r.load_mw; });
  const peakEntries = Object.entries(totalMw).sort((a,b) => b[1] - a[1]);
  const peakYr = peakEntries.length ? peakEntries[0][0] : '&mdash;';
  const peakMw = peakEntries.length ? Number(peakEntries[0][1]).toLocaleString() : '&mdash;';
  document.getElementById('vint-subtitle').textContent = `${quarter} snapshot by vintage · Peak: ${peakYr} at ${peakMw} MW`;

  const layout = {
    barmode: 'stack',
    xaxis: { title: 'Planning Year', tickmode: 'linear', dtick: 1 },
    yaxis: { title: 'Total Pipeline MW', tickformat: ',' },
    legend: { groupclick: 'toggleitem', orientation: 'v', x: 1.01, y: 1, font: { size: 11 } },
    plot_bgcolor: '#fafafa', paper_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 60, r: 220, t: 40, b: 60 }, hovermode: 'x unified',
    height: 520,
  };

  Plotly.react('vint-chart', traces, layout);
}

// ── Table builder ────────────────────────────────────────────────────────────
function buildTable(containerId, rows, cols) {
  const displayNames = {
    proj_id: 'ID', project_stage: 'Stage', segment: 'Segment', territory: 'Territory',
    announced_load_mw: 'Announced MW', initial_service_date: 'Service Date',
    project_age: 'Age (qtrs)', match_confidence: 'Confidence',
    report_quarter: 'Quarter', added_projects: 'Added', added_mw: 'Added MW',
    removed_projects: 'Removed', removed_mw: 'Removed MW', net_mw: 'Net MW',
    load_change_net_mw: 'Load Chg Net MW', stage_changes_count: 'Stage Changes',
    avg_delay_months: 'Avg Delay (mo)',
  };

  const numCols = new Set(['announced_load_mw','project_age','added_projects','added_mw','removed_projects','removed_mw','net_mw','load_change_net_mw','stage_changes_count','avg_delay_months']);

  let html = '<table class="data-table"><thead><tr>';
  cols.forEach(c => { html += `<th data-col="${c}">${displayNames[c] || c}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>';
    cols.forEach(c => {
      const val = r[c];
      const cls = numCols.has(c) ? 'num' : '';
      if (c === 'announced_load_mw' || c === 'added_mw' || c === 'removed_mw' || c === 'net_mw' || c === 'load_change_net_mw') {
        html += `<td class="${cls}">${fmt(val)}</td>`;
      } else if (c === 'avg_delay_months') {
        html += `<td class="${cls}">${val != null ? Number(val).toFixed(1) : '&mdash;'}</td>`;
      } else if (c === 'match_confidence') {
        html += `<td>${escHtml(val || '')}</td>`;
      } else {
        html += `<td>${escHtml(val)}</td>`;
      }
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById(containerId).innerHTML = html;

  // Column sorting
  document.querySelectorAll(`#${containerId} th`).forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      const tbody = th.closest('table').querySelector('tbody');
      const rowsArr = Array.from(tbody.querySelectorAll('tr'));
      const asc = th.dataset.asc !== 'true';
      th.dataset.asc = asc;
      rowsArr.sort((a, b) => {
        const va = a.children[th.cellIndex].textContent.trim();
        const vb = b.children[th.cellIndex].textContent.trim();
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      });
      rowsArr.forEach(tr => tbody.appendChild(tr));
    });
  });
}

// ── Init controls ────────────────────────────────────────────────────────────
// Snapshot controls
buildSelect('snap-quarter', QUARTERS, renderSnapshot);
buildCheckboxes('snap-stages', STAGES, STAGES, renderSnapshot);
buildCheckboxes('snap-segments', SEGMENTS, SEGMENTS, renderSnapshot);
document.getElementById('snap-seg-all').addEventListener('click', () => { setAll('snap-segments', true); renderSnapshot(); });
document.getElementById('snap-seg-none').addEventListener('click', () => { setAll('snap-segments', false); renderSnapshot(); });

// Evolution controls
buildCheckboxes('evo-quarters', QUARTERS, QUARTERS, renderEvolution);
buildCheckboxes('evo-stages', STAGES, STAGES, renderEvolution);
buildCheckboxes('evo-segments', SEGMENTS, SEGMENTS, renderEvolution);

const yrMin = YEARS[0], yrMax = YEARS[YEARS.length - 1];
const yrLo = document.getElementById('evo-year-lo');
const yrHi = document.getElementById('evo-year-hi');
yrLo.min = yrMin; yrLo.max = yrMax; yrLo.value = Math.max(2026, yrMin);
yrHi.min = yrMin; yrHi.max = yrMax; yrHi.value = Math.min(2032, yrMax);
document.getElementById('evo-year-min').textContent = yrMin;
document.getElementById('evo-year-max').textContent = yrMax;
function updateYearLabels() {
  const lo = parseInt(yrLo.value), hi = parseInt(yrHi.value);
  if (lo > hi) { yrLo.value = hi; yrHi.value = lo; }
  document.getElementById('evo-year-lo-val').textContent = Math.min(parseInt(yrLo.value), parseInt(yrHi.value));
  document.getElementById('evo-year-hi-val').textContent = Math.max(parseInt(yrLo.value), parseInt(yrHi.value));
}
yrLo.addEventListener('input', () => { updateYearLabels(); renderEvolution(); });
yrHi.addEventListener('input', () => { updateYearLabels(); renderEvolution(); });
updateYearLabels();

document.querySelectorAll('input[name="evo-agg"]').forEach(el => el.addEventListener('change', renderEvolution));
document.getElementById('evo-all').addEventListener('click', () => { setAll('evo-quarters', true); renderEvolution(); });
document.getElementById('evo-none').addEventListener('click', () => { setAll('evo-quarters', false); renderEvolution(); });
document.getElementById('evo-seg-all').addEventListener('click', () => { setAll('evo-segments', true); renderEvolution(); });
document.getElementById('evo-seg-none').addEventListener('click', () => { setAll('evo-segments', false); renderEvolution(); });

// Changes controls
const chgMetrics = document.getElementById('chg-metrics');
chgMetrics.innerHTML = Object.entries(METRIC_LABELS).map(([k,v]) =>
  `<label><input type="radio" name="chg-metric" value="${k}" ${k === 'net_mw' ? 'checked' : ''}> ${v}</label>`
).join('');
chgMetrics.querySelectorAll('input[type="radio"]').forEach(el => el.addEventListener('change', renderChanges));

// Build changes table
const chgCols = ['report_quarter','added_projects','added_mw','removed_projects','removed_mw','net_mw','load_change_net_mw','stage_changes_count','avg_delay_months'];
buildTable('chg-table-wrap', CHANGES, chgCols);

// Vintage controls
buildSelect('vint-quarter', QUARTERS, renderVintage);
buildCheckboxes('vint-stages', STAGES, STAGES, renderVintage);
buildCheckboxes('vint-vintages', VINTAGE_LABELS, VINTAGE_LABELS, renderVintage);
buildCheckboxes('vint-segments', SEGMENTS, SEGMENTS, renderVintage);
document.getElementById('vint-vint-all').addEventListener('click', () => { setAll('vint-vintages', true); renderVintage(); });
document.getElementById('vint-vint-none').addEventListener('click', () => { setAll('vint-vintages', false); renderVintage(); });
document.getElementById('vint-seg-all').addEventListener('click', () => { setAll('vint-segments', true); renderVintage(); });
document.getElementById('vint-seg-none').addEventListener('click', () => { setAll('vint-segments', false); renderVintage(); });

// ── Initial render ───────────────────────────────────────────────────────────
renderSnapshot();
</script>
</body>
</html>
"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html = HTML_TEMPLATE
    html = html.replace("__DATA_PLACEHOLDER__", json.dumps(EMBEDDED, indent=None, ensure_ascii=False, default=str))

    OUT.write_text(html, encoding="utf-8")
    ROOT.write_text(html, encoding="utf-8")
    print(f"Generated {OUT} ({OUT.stat().st_size:,} bytes)")
    print(f"  Rows: long={len(EMBEDDED['long'])}, changes={len(EMBEDDED['changes'])}, table={len(EMBEDDED['table'])}")
    print(f"  Added: {len(EMBEDDED['added'])}, Removed: {len(EMBEDDED['removed'])}")
    print(f"  Quarters: {len(EMBEDDED['meta']['quarters'])}, Years: {len(EMBEDDED['meta']['years'])}")


if __name__ == "__main__":
    main()