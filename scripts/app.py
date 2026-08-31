"""
Plotly Dash visualization for Georgia Power Large Load Economic Development Pipeline.
Loads data from outputs/combined/ and serves on http://localhost:8050
"""
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import plotly.express as _px
import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table, ctx
import dash_bootstrap_components as dbc

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
COMBINED_DIR = SCRIPT_DIR.parent / "outputs" / "combined"

df_proj = pd.read_csv(COMBINED_DIR / "pipeline_projects.csv")
df_changes = pd.read_csv(COMBINED_DIR / "pipeline_changes.csv")

QUARTER_ORDER = ["2024Q1","2024Q2","2024Q3","2024Q4",
                 "2025Q1","2025Q2","2025Q3","2025Q4","2026Q1","2026Q2"]


def _quarter_label(q):
    """'2026Q2' -> 'Q2 2026' for display."""
    return f"{q[4:]} {q[:4]}"


LOAD_COLS = [c for c in df_proj.columns if c.startswith("load_")]
ID_COLS = ["proj_id", "report_quarter", "quarter_first_seen", "project_age",
           "match_confidence", "segment", "class_type", "territory",
           "project_stage", "announced_load_mw", "initial_service_date",
           "new_project", "change_announced_load", "change_load_ramp",
           "change_project_stage", "change_initial_service_date"]

df_proj["segment"] = df_proj["segment"].fillna("unclassified")

df_long = df_proj.melt(
    id_vars=ID_COLS,
    value_vars=LOAD_COLS,
    var_name="year_col",
    value_name="load_mw",
)
df_long["planning_year"] = df_long["year_col"].str.extract(r"(\d{4})").astype(int)
df_long = df_long.drop(columns=["year_col"])
df_long = df_long[df_long["load_mw"].notna() & (df_long["load_mw"] > 0)]

df_long["report_quarter"] = pd.Categorical(df_long["report_quarter"], categories=QUARTER_ORDER, ordered=True)
df_long = df_long.sort_values(["report_quarter", "project_stage", "planning_year"])

df_changes["report_quarter"] = pd.Categorical(df_changes["report_quarter"], categories=QUARTER_ORDER, ordered=True)
df_changes = df_changes.sort_values("report_quarter")
df_changes["net_mw"] = df_changes["added_mw"].fillna(0) - df_changes["removed_mw"].fillna(0)

STAGES = ["Technical Review", "Request for Service", "Contract for Electric Service"]
STAGE_COLORS = {
    "Technical Review": "#5B8DB8",
    "Request for Service": "#E8963A",
    "Contract for Electric Service": "#4CAF7D",
}

# Vintage buckets: (label, shade_index). Stacked oldest-at-bottom → newest-at-top.
VINTAGE_BUCKETS = [
    ("4+ qtrs",     0),
    ("2–3 qtrs",    1),
    ("New (1 qtr)", 2),
]
VINTAGE_LABEL_ORDER = ["New (1 qtr)", "2–3 qtrs", "4+ qtrs"]

# Three shades per stage: index 0=dark(4+), 1=mid(2-3), 2=light(new)
VINTAGE_COLORS = {
    "Technical Review":              ["#2E5F8A", "#5B8DB8", "#9BBDD8"],
    "Request for Service":           ["#C4711A", "#E8963A", "#F4BF87"],
    "Contract for Electric Service": ["#2A7A55", "#4CAF7D", "#8ED4B0"],
}

ALL_SEGMENTS = sorted(df_long["segment"].dropna().unique().tolist())
ALL_YEARS = sorted(int(y) for y in df_long["planning_year"].unique())
QUARTERS_PRESENT = [q for q in QUARTER_ORDER if q in df_long["report_quarter"].unique().tolist()]
QUARTER_RANGE_LABEL = (
    f"{_quarter_label(QUARTERS_PRESENT[0])} – {_quarter_label(QUARTERS_PRESENT[-1])}"
    if QUARTERS_PRESENT else ""
)

METRIC_LABELS = {
    "net_mw": "Net MW Added (new projects − removed)",
    "load_change_net_mw": "Load Changes Net MW",
    "added_projects": "Projects Added (count)",
    "added_mw": "Projects Added (MW)",
    "removed_projects": "Projects Removed (count)",
    "removed_mw": "Projects Removed (MW)",
    "stage_changes_count": "Stage Changes (count)",
    "avg_delay_months": "Average Schedule Delay (months)",
}


def _vintage_bucket(age):
    if age == 1:
        return 2
    if age <= 3:
        return 1
    return 0


_VINT_IDX_TO_LABEL = {0: "4+ qtrs", 1: "2–3 qtrs", 2: "New (1 qtr)"}

# ---------------------------------------------------------------------------
# Pre-compute added / removed project-level frames
# ---------------------------------------------------------------------------

_FLOW_COLS = ["proj_id", "report_quarter", "project_stage",
              "project_age", "announced_load_mw", "segment"]

# Added: first appearance in our dataset (exclude 2024Q1 seed quarter)
df_added = df_proj[
    (df_proj["project_age"] == 1) & (df_proj["report_quarter"] != "2024Q1")
][_FLOW_COLS].copy()

# Removed: projects present in quarter N but absent in quarter N+1
_removed_rows = []
for _i in range(1, len(QUARTERS_PRESENT)):
    _prev_q = QUARTERS_PRESENT[_i - 1]
    _curr_q = QUARTERS_PRESENT[_i]
    _prev_ids = set(df_proj[df_proj["report_quarter"] == _prev_q]["proj_id"])
    _curr_ids = set(df_proj[df_proj["report_quarter"] == _curr_q]["proj_id"])
    _gone = _prev_ids - _curr_ids
    if _gone:
        _rows = df_proj[
            (df_proj["proj_id"].isin(_gone)) &
            (df_proj["report_quarter"] == _prev_q)
        ][_FLOW_COLS].copy()
        _rows["report_quarter"] = _curr_q   # tag as removed *in* this quarter
        _removed_rows.append(_rows)

df_removed = (pd.concat(_removed_rows, ignore_index=True)
              if _removed_rows else pd.DataFrame(columns=_FLOW_COLS))

for _df in (df_added, df_removed):
    _df["vintage_idx"] = _df["project_age"].apply(_vintage_bucket)
    _df["vintage_label"] = _df["vintage_idx"].map(_VINT_IDX_TO_LABEL)

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

LABEL_STYLE = {"fontWeight": "600", "fontSize": "13px", "marginBottom": "6px", "color": "#444"}
CARD_STYLE = {"backgroundColor": "#fff", "borderRadius": "8px", "padding": "20px",
              "boxShadow": "0 1px 4px rgba(0,0,0,.1)", "marginBottom": "20px"}


def ctrl_card(children):
    return html.Div(children, style=CARD_STYLE)


def _toggle_links(all_id, none_id):
    return html.Div([
        html.Span("All", style={"fontSize": "11px", "cursor": "pointer",
            "color": "#5B8DB8", "marginRight": "8px"}, id=all_id),
        html.Span("None", style={"fontSize": "11px", "cursor": "pointer",
            "color": "#5B8DB8"}, id=none_id),
    ], style={"marginBottom": "8px"})


def segment_checklist(id_prefix):
    return [
        html.Label("Segments", style=LABEL_STYLE),
        _toggle_links(f"{id_prefix}-seg-all", f"{id_prefix}-seg-none"),
        dcc.Checklist(
            id=f"{id_prefix}-segments",
            options=[{"label": f"  {s}", "value": s} for s in ALL_SEGMENTS],
            value=ALL_SEGMENTS,
            labelStyle={"display": "block", "marginBottom": "3px", "fontSize": "13px"},
        ),
    ]


def vintage_checklist(id_prefix):
    return [
        html.Label("Vintage", style=LABEL_STYLE),
        _toggle_links(f"{id_prefix}-vint-all", f"{id_prefix}-vint-none"),
        dcc.Checklist(
            id=f"{id_prefix}-vintages",
            options=[{"label": f"  {v}", "value": v} for v in VINTAGE_LABEL_ORDER],
            value=VINTAGE_LABEL_ORDER,
            labelStyle={"display": "block", "marginBottom": "3px", "fontSize": "13px"},
        ),
    ]


# ---------------------------------------------------------------------------
# App + layout
# ---------------------------------------------------------------------------

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="GA Power Large Load Pipeline",
)

app.layout = html.Div([
    dcc.Store(id='snap-anim-store', data={'playing': False}),
    dcc.Interval(id='snap-anim-interval', interval=1500, disabled=True),
    html.Div([
        html.H2("Georgia Power Large Load Economic Development Pipeline",
                style={"margin": "0", "fontWeight": "700", "fontSize": "22px", "color": "#1a1a2e"}),
        html.P(f"Docket 55378 · Quarterly Reports {QUARTER_RANGE_LABEL}",
               style={"margin": "4px 0 0", "color": "#666", "fontSize": "13px"}),
    ], style={"padding": "20px 30px 16px", "borderBottom": "2px solid #e8e8e8",
              "backgroundColor": "#fff"}),

    dcc.Tabs(value="snapshot", children=[

        # ------------------------------------------------------------------
        # Tab 1 — Snapshot
        # ------------------------------------------------------------------
        dcc.Tab(label="Pipeline Snapshot", value="snapshot", children=[
            html.Div([
                dbc.Row([
                    dbc.Col(ctrl_card([
                        html.Label("Report Quarter", style=LABEL_STYLE),
                        dcc.Dropdown(
                            id="snap-quarter",
                            options=[{"label": q, "value": q} for q in QUARTERS_PRESENT],
                            value=QUARTERS_PRESENT[-1],
                            clearable=False,
                            style={"width": "200px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        html.Label("Pipeline Stages", style=LABEL_STYLE),
                        dcc.Checklist(
                            id="snap-stages",
                            options=[{"label": f"  {s}", "value": s} for s in STAGES],
                            value=STAGES,
                            labelStyle={"display": "block", "marginBottom": "4px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        *segment_checklist("snap"),
                        html.Hr(),
                        html.Label("Animate", style=LABEL_STYLE),
                        html.Div([
                            html.Button("⏮", id="snap-prev", n_clicks=0,
                                        style={"width": "32px", "height": "32px", "borderRadius": "50%",
                                               "border": "1px solid #ddd", "background": "#fff",
                                               "cursor": "pointer", "fontSize": "14px"}),
                            html.Button("▶", id="snap-play", n_clicks=0,
                                        style={"width": "32px", "height": "32px", "borderRadius": "50%",
                                               "border": "1px solid #ddd", "background": "#fff",
                                               "cursor": "pointer", "fontSize": "14px", "margin": "0 4px"}),
                            html.Button("⏭", id="snap-next", n_clicks=0,
                                        style={"width": "32px", "height": "32px", "borderRadius": "50%",
                                               "border": "1px solid #ddd", "background": "#fff",
                                               "cursor": "pointer", "fontSize": "14px"}),
                        ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                    ]), width=3),
                    dbc.Col([
                        html.Div(id="snap-subtitle",
                                 style={"fontSize": "14px", "color": "#555", "marginBottom": "12px"}),
                        dcc.Graph(id="snap-chart", style={"height": "520px"}),
                    ], width=9),
                ]),
                ctrl_card([
                    html.Label("Projects in selected quarter", style=LABEL_STYLE),
                    dash_table.DataTable(
                        id="snap-table",
                        columns=[
                            {"name": "ID", "id": "proj_id"},
                            {"name": "Stage", "id": "project_stage"},
                            {"name": "Segment", "id": "segment"},
                            {"name": "Territory", "id": "territory"},
                            {"name": "Announced MW", "id": "announced_load_mw",
                             "type": "numeric", "format": {"specifier": ",.0f"}},
                            {"name": "Service Date", "id": "initial_service_date"},
                            {"name": "Age (qtrs)", "id": "project_age", "type": "numeric"},
                            {"name": "Confidence", "id": "match_confidence"},
                        ],
                        page_size=15,
                        sort_action="native",
                        filter_action="native",
                        style_table={"overflowX": "auto"},
                        style_header={"backgroundColor": "#f0f2f5", "fontWeight": "bold", "fontSize": "12px"},
                        style_cell={"fontSize": "12px", "padding": "6px 12px", "textAlign": "left"},
                        style_cell_conditional=[
                            {"if": {"column_id": c}, "textAlign": "right"}
                            for c in ["announced_load_mw", "project_age"]
                        ],
                    ),
                ]),
            ], style={"padding": "24px 30px"}),
        ]),

        # ------------------------------------------------------------------
        # Tab 2 — Evolution
        # ------------------------------------------------------------------
        dcc.Tab(label="Pipeline Evolution", value="evolution", children=[
            html.Div([
                dbc.Row([
                    dbc.Col(ctrl_card([
                        html.Label("Forecast Quarters", style=LABEL_STYLE),
                        _toggle_links("evo-all", "evo-none"),
                        dcc.Checklist(
                            id="evo-quarters",
                            options=[{"label": f"  {q}", "value": q} for q in QUARTERS_PRESENT],
                            value=QUARTERS_PRESENT,
                            labelStyle={"display": "block", "marginBottom": "3px", "fontSize": "13px"},
                        ),
                    ]), width=3),
                    dbc.Col(ctrl_card([
                        html.Label("Pipeline Stages", style=LABEL_STYLE),
                        dcc.Checklist(
                            id="evo-stages",
                            options=[{"label": f"  {s}", "value": s} for s in STAGES],
                            value=STAGES,
                            labelStyle={"display": "block", "marginBottom": "4px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        html.Label("Planning Years", style=LABEL_STYLE),
                        dcc.RangeSlider(
                            id="evo-year-range",
                            min=ALL_YEARS[0], max=ALL_YEARS[-1],
                            value=[2026, 2032],
                            step=1,
                            marks={yr: str(yr) for yr in ALL_YEARS[::2]},
                            tooltip={"placement": "bottom"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        html.Label("Show stages", style=LABEL_STYLE),
                        dcc.RadioItems(
                            id="evo-agg",
                            options=[
                                {"label": "  Combined (sum all selected)", "value": "sum"},
                                {"label": "  Separate lines per stage", "value": "each"},
                            ],
                            value="sum",
                            labelStyle={"display": "block", "marginBottom": "4px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        *segment_checklist("evo"),
                    ]), width=9),
                ]),
                dcc.Graph(id="evo-chart", style={"height": "540px"}),
            ], style={"padding": "24px 30px"}),
        ]),

        # ------------------------------------------------------------------
        # Tab 3 — QoQ Changes
        # ------------------------------------------------------------------
        dcc.Tab(label="Quarter-over-Quarter Changes", value="changes", children=[
            html.Div([
                # Aggregate metrics (net MW, load changes, stage changes, delays)
                ctrl_card([
                    html.Label("Aggregate Metric", style=LABEL_STYLE),
                    dcc.RadioItems(
                        id="chg-metric",
                        options=[{"label": f"  {v}", "value": k}
                                 for k, v in METRIC_LABELS.items()],
                        value="net_mw",
                        labelStyle={"display": "inline-block",
                                    "marginRight": "20px", "marginBottom": "4px"},
                    ),
                ]),
                dcc.Graph(id="chg-chart", style={"height": "420px"}),

                ctrl_card([
                    html.Label("Full quarterly change summary", style=LABEL_STYLE),
                    dash_table.DataTable(
                        id="chg-table",
                        columns=[
                            {"name": "Quarter", "id": "report_quarter"},
                            {"name": "Added Projects", "id": "added_projects", "type": "numeric"},
                            {"name": "Added MW", "id": "added_mw", "type": "numeric",
                             "format": {"specifier": ",.0f"}},
                            {"name": "Removed Projects", "id": "removed_projects", "type": "numeric"},
                            {"name": "Removed MW", "id": "removed_mw", "type": "numeric",
                             "format": {"specifier": ",.0f"}},
                            {"name": "Net MW", "id": "net_mw", "type": "numeric",
                             "format": {"specifier": ",.0f"}},
                            {"name": "Load Chg Net MW", "id": "load_change_net_mw",
                             "type": "numeric", "format": {"specifier": ",.0f"}},
                            {"name": "Stage Changes", "id": "stage_changes_count", "type": "numeric"},
                            {"name": "Avg Delay (mo)", "id": "avg_delay_months",
                             "type": "numeric", "format": {"specifier": ".1f"}},
                        ],
                        data=df_changes.to_dict("records"),
                        style_table={"overflowX": "auto"},
                        style_header={"backgroundColor": "#f0f2f5", "fontWeight": "bold",
                                      "fontSize": "12px"},
                        style_cell={"fontSize": "12px", "padding": "6px 12px",
                                    "textAlign": "right"},
                        style_cell_conditional=[
                            {"if": {"column_id": "report_quarter"}, "textAlign": "left"}],
                        style_data_conditional=[
                            {"if": {"filter_query": "{net_mw} > 0", "column_id": "net_mw"},
                             "color": "#2e7d32"},
                            {"if": {"filter_query": "{net_mw} < 0", "column_id": "net_mw"},
                             "color": "#c62828"},
                        ],
                    ),
                ]),
            ], style={"padding": "24px 30px"}),
        ]),

        # ------------------------------------------------------------------
        # Tab 4 — Snapshot by Vintage
        # ------------------------------------------------------------------
        dcc.Tab(label="Snapshot by Vintage", value="vintage", children=[
            html.Div([
                dbc.Row([
                    dbc.Col(ctrl_card([
                        html.Label("Report Quarter", style=LABEL_STYLE),
                        dcc.Dropdown(
                            id="vint-quarter",
                            options=[{"label": q, "value": q} for q in QUARTERS_PRESENT],
                            value=QUARTERS_PRESENT[-1],
                            clearable=False,
                            style={"width": "200px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        html.Label("Pipeline Stages", style=LABEL_STYLE),
                        dcc.Checklist(
                            id="vint-stages",
                            options=[{"label": f"  {s}", "value": s} for s in STAGES],
                            value=STAGES,
                            labelStyle={"display": "block", "marginBottom": "4px"},
                        ),
                        html.Div(style={"marginTop": "12px"}),
                        *vintage_checklist("vint"),
                        html.Div(style={"marginTop": "12px"}),
                        *segment_checklist("vint"),
                    ]), width=3),
                    dbc.Col([
                        html.Div(id="vint-subtitle",
                                 style={"fontSize": "14px", "color": "#555", "marginBottom": "12px"}),
                        dcc.Graph(id="vint-chart", style={"height": "520px"}),
                    ], width=9),
                ]),
            ], style={"padding": "24px 30px"}),
        ]),

    ], style={"margin": "0 30px"}),

], style={"fontFamily": "'Segoe UI', Arial, sans-serif",
          "backgroundColor": "#f5f6fa", "minHeight": "100vh"})


# ---------------------------------------------------------------------------
# Callbacks — Tab 1 Snapshot
# ---------------------------------------------------------------------------

@app.callback(
    Output("snap-segments", "value"),
    Input("snap-seg-all", "n_clicks"),
    Input("snap-seg-none", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_snap_segments(*_):
    return ALL_SEGMENTS if ctx.triggered_id == "snap-seg-all" else []


@app.callback(
    Output("snap-chart", "figure"),
    Output("snap-subtitle", "children"),
    Output("snap-table", "data"),
    Input("snap-quarter", "value"),
    Input("snap-stages", "value"),
    Input("snap-segments", "value"),
    Input("snap-anim-store", "data"),
)
def update_snapshot(quarter, stages, segments, anim_state):
    if not stages or not segments:
        return go.Figure(), "", []

    sub = df_long[
        (df_long["report_quarter"] == quarter) &
        (df_long["project_stage"].isin(stages)) &
        (df_long["segment"].isin(segments))
    ].copy()

    total_mw = sub.groupby("planning_year")["load_mw"].sum()

    fig = go.Figure()
    for stage in reversed(STAGES):
        s = (sub[sub["project_stage"] == stage]
             .groupby("planning_year")["load_mw"].sum()
             .reset_index()
             .sort_values("planning_year"))
        fig.add_trace(go.Bar(
            x=s["planning_year"], y=s["load_mw"],
            name=stage, marker_color=STAGE_COLORS[stage],
            visible=True if stage in stages else "legendonly",
            hovertemplate="<b>%{x}</b><br>" + stage + ": %{y:,.0f} MW<extra></extra>",
        ))

    yaxis = dict(title="Total Pipeline MW", tickformat=",")
    if anim_state and anim_state.get("playing"):
        final_q = QUARTERS_PRESENT[-1]
        final_sub = df_long[
            (df_long["report_quarter"] == final_q) &
            (df_long["project_stage"].isin(stages)) &
            (df_long["segment"].isin(segments))
        ]
        final_max = final_sub.groupby("planning_year")["load_mw"].sum().max()
        if final_max > 0:
            yaxis["range"] = [0, final_max * 1.05]
            yaxis["autorange"] = False

    layout_kwargs = dict(
        barmode="stack",
        xaxis=dict(title="Planning Year", tickmode="linear", dtick=1),
        yaxis=yaxis,
        legend=dict(title="Pipeline Stage", orientation="h",
                    yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#fafafa", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=20, t=60, b=60), hovermode="x unified",
    )
    if anim_state and anim_state.get("playing"):
        layout_kwargs["transition"] = {"duration": 800, "easing": "cubic-in-out"}
    fig.update_layout(**layout_kwargs)

    peak_yr = int(total_mw.idxmax()) if not total_mw.empty else "—"
    peak_mw = f"{total_mw.max():,.0f}" if not total_mw.empty else "—"
    subtitle = f"{quarter} snapshot · Peak planning year: {peak_yr} at {peak_mw} MW total"

    proj_sub = df_proj[
        (df_proj["report_quarter"] == quarter) &
        (df_proj["project_stage"].isin(stages)) &
        (df_proj["segment"].isin(segments))
    ][["proj_id", "project_stage", "segment", "territory",
       "announced_load_mw", "initial_service_date", "project_age", "match_confidence"]]

    return fig, subtitle, proj_sub.to_dict("records")


@app.callback(
    Output("snap-anim-interval", "disabled"),
    Output("snap-anim-store", "data"),
    Output("snap-play", "children"),
    Input("snap-play", "n_clicks"),
    Input("snap-prev", "n_clicks"),
    Input("snap-next", "n_clicks"),
    Input("snap-anim-interval", "n_intervals"),
    Input("snap-stages", "value"),
    Input("snap-segments", "value"),
    State("snap-quarter", "value"),
    State("snap-anim-store", "data"),
    prevent_initial_call=True,
)
def toggle_snap_animation(play_nc, prev_nc, next_nc, n_intervals, stages, segments, quarter, anim_state):
    triggered = ctx.triggered_id
    state = dict(anim_state) if anim_state else {"playing": False}

    if triggered in ("snap-stages", "snap-segments"):
        state["playing"] = False
        return True, state, "▶"

    if triggered == "snap-play":
        state["playing"] = not state.get("playing", False)
        return not state["playing"], state, "⏸" if state["playing"] else "▶"

    if triggered in ("snap-prev", "snap-next"):
        state["playing"] = False
        idx = QUARTERS_PRESENT.index(quarter) if quarter in QUARTERS_PRESENT else len(QUARTERS_PRESENT) - 1
        if triggered == "snap-prev":
            state["target"] = QUARTERS_PRESENT[max(0, idx - 1)]
        else:
            state["target"] = QUARTERS_PRESENT[min(len(QUARTERS_PRESENT) - 1, idx + 1)]
        return True, state, "▶"

    if triggered == "snap-anim-interval" and state.get("playing"):
        idx = QUARTERS_PRESENT.index(quarter) if quarter in QUARTERS_PRESENT else -1
        if idx < len(QUARTERS_PRESENT) - 1:
            state["target"] = QUARTERS_PRESENT[idx + 1]
            return False, state, "⏸"
        else:
            state["playing"] = False
            return True, state, "▶"

    return not state.get("playing", False), state, "⏸" if state.get("playing") else "▶"


@app.callback(
    Output("snap-quarter", "value", allow_duplicate=True),
    Input("snap-anim-store", "data"),
    prevent_initial_call=True,
)
def sync_snap_quarter(anim_state):
    if anim_state and anim_state.get("target"):
        return anim_state["target"]
    return dash.no_update


# ---------------------------------------------------------------------------
# Callbacks — Tab 2 Evolution
# ---------------------------------------------------------------------------

_PALETTE = _px.colors.qualitative.D3 + _px.colors.qualitative.Plotly
QUARTER_COLORS = {q: _PALETTE[i % len(_PALETTE)] for i, q in enumerate(QUARTER_ORDER)}


@app.callback(
    Output("evo-quarters", "value"),
    Input("evo-all", "n_clicks"),
    Input("evo-none", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_quarters(*_):
    return QUARTERS_PRESENT if ctx.triggered_id == "evo-all" else []


@app.callback(
    Output("evo-segments", "value"),
    Input("evo-seg-all", "n_clicks"),
    Input("evo-seg-none", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_evo_segments(*_):
    return ALL_SEGMENTS if ctx.triggered_id == "evo-seg-all" else []


@app.callback(
    Output("evo-chart", "figure"),
    Input("evo-quarters", "value"),
    Input("evo-stages", "value"),
    Input("evo-year-range", "value"),
    Input("evo-agg", "value"),
    Input("evo-segments", "value"),
)
def update_evolution(quarters, stages, year_range, agg, segments):
    if not stages or not quarters or not segments:
        return go.Figure()
    yr_min, yr_max = year_range

    sub = df_long[
        (df_long["report_quarter"].isin(quarters)) &
        (df_long["project_stage"].isin(stages)) &
        (df_long["planning_year"] >= yr_min) &
        (df_long["planning_year"] <= yr_max) &
        (df_long["segment"].isin(segments))
    ].copy()

    fig = go.Figure()
    quarters_sorted = [q for q in QUARTER_ORDER if q in quarters]

    if agg == "sum":
        grouped = (sub.groupby(["report_quarter", "planning_year"], observed=True)
                   ["load_mw"].sum().reset_index())
        for q in quarters_sorted:
            s = grouped[grouped["report_quarter"] == q].sort_values("planning_year")
            fig.add_trace(go.Scatter(
                x=s["planning_year"], y=s["load_mw"],
                mode="lines+markers", name=q,
                line=dict(color=QUARTER_COLORS[q], width=2.5),
                marker=dict(size=7),
                hovertemplate=f"<b>%{{x}}</b><br>{q}: %{{y:,.0f}} MW<extra></extra>",
            ))
        stage_label = "all stages" if len(stages) == 3 else " + ".join(stages)
        ylabel = f"Total Pipeline MW ({stage_label})"
    else:
        grouped = (sub.groupby(["report_quarter", "project_stage", "planning_year"], observed=True)
                   ["load_mw"].sum().reset_index())
        dashes = ["solid", "dash", "dot"]
        for q in quarters_sorted:
            for i, stage in enumerate(STAGES):
                if stage not in stages:
                    continue
                s = grouped[(grouped["report_quarter"] == q) &
                            (grouped["project_stage"] == stage)].sort_values("planning_year")
                if s.empty or s["load_mw"].sum() == 0:
                    continue
                fig.add_trace(go.Scatter(
                    x=s["planning_year"], y=s["load_mw"],
                    mode="lines+markers",
                    name=f"{q} · {stage}",
                    line=dict(color=QUARTER_COLORS[q], width=1.8, dash=dashes[i]),
                    marker=dict(size=5),
                    hovertemplate=f"<b>%{{x}}</b><br>{q} {stage}: %{{y:,.0f}} MW<extra></extra>",
                ))
        ylabel = "Pipeline MW by Stage"

    fig.update_layout(
        xaxis=dict(title="Planning Year", tickmode="linear", dtick=1),
        yaxis=dict(title=ylabel, tickformat=","),
        legend=dict(orientation="v", x=1.01, y=1, font=dict(size=11)),
        plot_bgcolor="#fafafa", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=200, t=40, b=60), hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Callbacks — Tab 3 QoQ Changes
# ---------------------------------------------------------------------------

_FLOW_METRICS = {
    "added_projects": (df_added,   "count", "Projects Added"),
    "added_mw":       (df_added,   "mw",    "Projects Added"),
    "removed_projects": (df_removed, "count", "Projects Removed"),
    "removed_mw":     (df_removed, "mw",    "Projects Removed"),
}


@app.callback(
    Output("chg-chart", "figure"),
    Input("chg-metric", "value"),
)
def update_changes(metric):
    qs = [q for q in QUARTERS_PRESENT if q != "2024Q1"]

    if metric in _FLOW_METRICS:
        df_flow, view, flow_title = _FLOW_METRICS[metric]
        ylabel = "Announced MW" if view == "mw" else "Project Count"
        unit = "MW" if view == "mw" else "projects"
        fig = go.Figure()
        for stage in reversed(STAGES):
            colors = VINTAGE_COLORS[stage]
            for vlabel, vidx in VINTAGE_BUCKETS:
                mask = (
                    df_flow["report_quarter"].isin(qs) &
                    (df_flow["project_stage"] == stage) &
                    (df_flow["vintage_label"] == vlabel)
                )
                sub = df_flow[mask]
                if sub.empty:
                    continue
                if view == "mw":
                    grp = sub.groupby("report_quarter")["announced_load_mw"].sum().reindex(qs, fill_value=0)
                else:
                    grp = sub.groupby("report_quarter").size().reindex(qs, fill_value=0)
                fig.add_trace(go.Bar(
                    x=qs, y=grp.values,
                    name=f"{stage[:3]}… · {vlabel}",
                    marker_color=colors[vidx],
                    legendgroup=stage,
                    legendgrouptitle_text=stage if vidx == 0 else None,
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>{stage}<br>{vlabel}: %{{y:,.0f}} {unit}<extra></extra>"
                    ),
                ))
        fig.update_layout(
            barmode="stack",
            xaxis=dict(title="Report Quarter"),
            yaxis=dict(title=ylabel, tickformat=","),
            legend=dict(groupclick="toggleitem", orientation="v",
                        x=1.01, y=1, font=dict(size=11)),
            plot_bgcolor="#fafafa", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=60, r=200, t=20, b=50),
        )
        return fig

    # Aggregate metric path
    sub = df_changes.dropna(subset=[metric]).sort_values("report_quarter")
    colors = ["#c62828" if v < 0 else "#2e7d32" if v > 0 else "#999"
              for v in sub[metric]]
    fig = go.Figure(go.Bar(
        x=sub["report_quarter"].astype(str), y=sub[metric],
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>" + METRIC_LABELS[metric] + ": %{y:,.1f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        xaxis=dict(title="Report Quarter"),
        yaxis=dict(title=METRIC_LABELS[metric], tickformat=","),
        plot_bgcolor="#fafafa", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=20, t=20, b=50),
    )
    return fig


# ---------------------------------------------------------------------------
# Callbacks — Tab 4 Snapshot by Vintage
# ---------------------------------------------------------------------------

@app.callback(
    Output("vint-segments", "value"),
    Input("vint-seg-all", "n_clicks"),
    Input("vint-seg-none", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_vint_segments(*_):
    return ALL_SEGMENTS if ctx.triggered_id == "vint-seg-all" else []


@app.callback(
    Output("vint-vintages", "value"),
    Input("vint-vint-all", "n_clicks"),
    Input("vint-vint-none", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_vint_vintages(*_):
    return VINTAGE_LABEL_ORDER if ctx.triggered_id == "vint-vint-all" else []


@app.callback(
    Output("vint-chart", "figure"),
    Output("vint-subtitle", "children"),
    Input("vint-quarter", "value"),
    Input("vint-stages", "value"),
    Input("vint-vintages", "value"),
    Input("vint-segments", "value"),
)
def update_vintage(quarter, stages, vintages, segments):
    if not stages or not segments or not vintages:
        return go.Figure(), ""

    sub = df_long[
        (df_long["report_quarter"] == quarter) &
        (df_long["project_stage"].isin(stages)) &
        (df_long["segment"].isin(segments))
    ].copy()

    sub["vintage_idx"] = sub["project_age"].apply(_vintage_bucket)
    sub["vintage_label"] = sub["vintage_idx"].map(_VINT_IDX_TO_LABEL)
    sub = sub[sub["vintage_label"].isin(vintages)]

    fig = go.Figure()
    for stage in reversed(STAGES):
        if stage not in stages:
            continue
        colors = VINTAGE_COLORS[stage]
        for vlabel, vidx in VINTAGE_BUCKETS:
            if vlabel not in vintages:
                continue
            s = (sub[(sub["project_stage"] == stage) & (sub["vintage_label"] == vlabel)]
                 .groupby("planning_year")["load_mw"].sum()
                 .reset_index()
                 .sort_values("planning_year"))
            if s.empty or s["load_mw"].sum() == 0:
                continue
            fig.add_trace(go.Bar(
                x=s["planning_year"], y=s["load_mw"],
                name=f"{stage[:3]}… · {vlabel}",
                marker_color=colors[vidx],
                legendgroup=stage,
                legendgrouptitle_text=stage if vidx == 0 else None,
                hovertemplate=(
                    f"<b>%{{x}}</b><br>{stage}<br>{vlabel}: %{{y:,.0f}} MW<extra></extra>"
                ),
            ))

    total_mw = sub.groupby("planning_year")["load_mw"].sum()
    peak_yr = int(total_mw.idxmax()) if not total_mw.empty else "—"
    peak_mw = f"{total_mw.max():,.0f}" if not total_mw.empty else "—"
    subtitle = f"{quarter} snapshot by vintage · Peak: {peak_yr} at {peak_mw} MW"

    fig.update_layout(
        barmode="stack",
        xaxis=dict(title="Planning Year", tickmode="linear", dtick=1),
        yaxis=dict(title="Total Pipeline MW", tickformat=","),
        legend=dict(groupclick="toggleitem", orientation="v",
                    x=1.01, y=1, font=dict(size=11)),
        plot_bgcolor="#fafafa", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=220, t=60, b=60), hovermode="x unified",
    )
    return fig, subtitle


if __name__ == "__main__":
    app.run(debug=False, port=8050)
