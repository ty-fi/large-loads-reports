"""
assign_project_ids.py

Tracks individual large load projects across quarterly GA PSC Docket 55378 reports.
Project names are redacted, so identity is inferred from each filing's own
bookkeeping, which reconciles exactly in every quarter but two:

    previous projects - Removed Projects + (New Project? = Y) == current projects

Each quarter is solved as one minimum-cost assignment (scipy's
linear_sum_assignment) between the previous quarter's projects and the current
ones, with slots for "new", "removed" (one per Removed Projects row) and
"vanished without explanation". A pairing costs nothing when every attribute the
current row does NOT flag as changed is identical, and every attribute it DOES
flag changed from a value the matching change sheet (Load Change, Initial
Service Change, Stage Change, Ramp Change) lists. See the W_* / COST_* constants.

match_confidence: seed (first quarter), new, exact (cost 0), high (< W_LOAD),
low (a substantive attribute disagrees).

Output: outputs/combined/pipeline_projects.csv
"""

import datetime
import re
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

SCRIPT_DIR = Path(__file__).parent
INPUTS_DIR = SCRIPT_DIR.parent / "inputs"
OUTPUTS_DIR = SCRIPT_DIR.parent / "outputs"
WORKBOOKS_DIR = INPUTS_DIR / "workbooks"
COMBINED_DIR = OUTPUTS_DIR / "combined"

QUARTER_ORDER = ["2024Q1", "2024Q2", "2024Q3", "2024Q4",
                 "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"]

LOAD_YEARS = list(range(2023, 2038))

STAGE_ALIASES = {
    "contract for electric service": "Contract for Electric Service",
    "request for service": "Request for Service",
    "request for electric service": "Request for Service",
    "technical review": "Technical Review",
}

SEGMENT_ALIASES = {
    "data centers": "data center",
    "data center/crypto": "data center",
    "clean energy technology": "clean energy tech",
}


# ── Normalization ─────────────────────────────────────────────────────────────

KNOWN_STAGES = set(STAGE_ALIASES.values())

_warned_stages = set()


def norm_stage(raw):
    if not raw:
        return ""
    cleaned = re.sub(r'[\s\d*]+$', '', str(raw)).strip()
    stage = STAGE_ALIASES.get(cleaned.lower(), cleaned)
    if stage and stage not in KNOWN_STAGES:
        # Footnote text can land in the Project Stage column (first seen in the
        # Q2 2026 filing). Reject it, but say so rather than dropping silently.
        if stage not in _warned_stages:
            _warned_stages.add(stage)
            print(f"    WARNING: ignoring unrecognized Project Stage value: {stage[:70]!r}")
        return ""
    return stage

def norm_segment(s):
    if not s:
        return ""
    return SEGMENT_ALIASES.get(s.strip().lower(), s.strip().lower())

def norm_load(v):
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None

def norm_date(s):
    """Normalize an in-service date to a 'Q<n> YYYY' label.

    Quarters through Q1 2026 wrote these as text ('Q4 2027'). The Q2 2026
    workbook switched to real Excel datetimes (2027-12-01), which the old
    regex passed through verbatim -- so no fingerprint ever matched across
    that boundary. Accept both forms.
    """
    if not s:
        return ""
    if isinstance(s, (datetime.datetime, datetime.date)):
        return f"Q{(s.month - 1) // 3 + 1} {s.year}"
    text = str(s).strip()
    m = re.search(r'Q([1-4])\s*(\d{4})', text, re.IGNORECASE)
    if m:
        return f"Q{m.group(1)} {m.group(2)}"
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        return f"Q{(month - 1) // 3 + 1} {year}"
    return text

def norm_flag(v):
    return "Y" if str(v).strip().upper() == "Y" else ""


# ── Low-level sheet helpers ───────────────────────────────────────────────────

def load_ws_rows(ws):
    return list(ws.iter_rows(values_only=True))

def find_header_row(rows):
    for i, row in enumerate(rows):
        if any(c and re.search(r'project.?(name|stage)', str(c), re.IGNORECASE) for c in row):
            return i
    return None

def name_base(headers):
    """Index of the 'Project Name' column in a change sheet.

    Change-sheet columns used to be read positionally from column 0. The Q2 2026
    workbook inserted a leading blank column, which shifted every field right by
    one and made all change metrics parse as empty. Anchoring on Project Name
    keeps both layouts working.
    """
    idx = find_col(headers, r'project.?name')
    return idx if idx is not None else 0


_NON_PROJECT_NAME = re.compile(r'^(total\b|note\b|\*|\d+\.\s)', re.IGNORECASE)


def is_project_row(row, base):
    """False for change-sheet 'Total' rows and footnotes in the name column.

    A 'Total' row on Removed Projects parses as a removal whose load equals the
    sheet sum, which can pop an unrelated project out of the matching pool.
    """
    if not row or base >= len(row) or row[base] is None:
        return False
    return not _NON_PROJECT_NAME.match(str(row[base]).strip())


def find_col(headers, *patterns):
    for pat in patterns:
        for i, h in enumerate(headers):
            if h and re.search(pat, str(h), re.IGNORECASE):
                return i
    return None


# ── Excel Main sheet parser ───────────────────────────────────────────────────

def parse_excel_main(ws, quarter):
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    headers = rows[hi]

    # Year columns (bare 4-digit integers/strings)
    year_cols = {}
    for i, h in enumerate(headers):
        m = re.fullmatch(r'(\d{4})', str(h).strip()) if h is not None else None
        if m:
            yr = int(m.group(1))
            if 2020 <= yr <= 2040:
                year_cols[i] = yr

    # Change flag columns appear after the last year column in a fixed order:
    # New Project?, Announced Load (chg), Load Ramp (chg), Project Stage (chg), Initial Service Date (chg)
    last_yr_idx = max(year_cols.keys()) if year_cols else -1
    flag_positions = [i for i, h in enumerate(headers) if i > last_yr_idx and h is not None]
    flag_keys = ['new_project', 'change_announced_load', 'change_load_ramp',
                 'change_project_stage', 'change_initial_service_date']
    flag_col = {k: flag_positions[i] if i < len(flag_positions) else None
                for i, k in enumerate(flag_keys)}

    seg_col   = find_col(headers, r'^segment$')
    class_col = find_col(headers, r'^class$', r'facility.?type')
    terr_col  = find_col(headers, r'^territory$')
    stage_col = find_col(headers, r'project.?stage')
    load_col  = find_col(headers, r'announced.?load')
    date_col  = find_col(headers, r'in.?service.?date', r'initial.?service')

    projects = []
    for row in rows[hi + 1:]:
        if not any(c is not None for c in row):
            continue
        stage_val = row[stage_col] if stage_col is not None else None
        if stage_val is None:
            continue
        stage = norm_stage(stage_val)
        if not stage:
            continue

        seg   = norm_segment(str(row[seg_col]).strip() if seg_col is not None and row[seg_col] else "")
        cls   = str(row[class_col]).strip() if class_col is not None and row[class_col] else ""
        terr  = str(row[terr_col]).strip() if terr_col is not None and row[terr_col] else ""
        load  = norm_load(row[load_col] if load_col is not None else None)
        date  = norm_date(row[date_col] if date_col is not None else None)

        ramp = {}
        for ci, yr in year_cols.items():
            v = row[ci]
            try:
                ramp[yr] = float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                ramp[yr] = 0.0

        def get_flag(k):
            idx = flag_col.get(k)
            if idx is None:
                return ""
            return norm_flag(row[idx]) if row[idx] is not None else ""

        projects.append({
            'segment': seg, 'class_type': cls, 'territory': terr,
            'project_stage': stage, 'announced_load': load,
            'initial_service_date': date, 'ramp': ramp,
            'new_project':                   get_flag('new_project'),
            'change_announced_load':         get_flag('change_announced_load'),
            'change_load_ramp':              get_flag('change_load_ramp'),
            'change_project_stage':          get_flag('change_project_stage'),
            'change_initial_service_date':   get_flag('change_initial_service_date'),
        })
    return projects


# ── Excel change sheet parsers ────────────────────────────────────────────────

def parse_excel_load_changes(ws):
    """Return list of (prev_load, new_load)."""
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    base = name_base(rows[hi])
    result = []
    for row in rows[hi + 1:]:
        if base + 2 >= len(row) or not is_project_row(row, base):
            continue
        new_load  = norm_load(row[base + 1])
        prev_load = norm_load(row[base + 2])
        if prev_load is not None and new_load is not None and prev_load != new_load:
            result.append((prev_load, new_load))
    return result

def parse_excel_date_changes(ws):
    """Return list of (prev_date, new_date)."""
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    base = name_base(rows[hi])
    result = []
    for row in rows[hi + 1:]:
        if base + 2 >= len(row) or not is_project_row(row, base):
            continue
        new_date  = norm_date(row[base + 1])
        prev_date = norm_date(row[base + 2])
        if prev_date and new_date and prev_date != new_date:
            result.append((prev_date, new_date))
    return result

def parse_excel_ramp_changes(ws):
    """Return list of (prev_ramp_dict, new_ramp_dict).

    Sheet layout (row 0 = section labels, row 1 = year headers):
      col 0          : Project Name
      cols 1-15      : new ramp (current quarter), years 2023-2037
      cols 16-30     : previous ramp, years 2023-2037
    """
    rows = load_ws_rows(ws)
    # Header is row 1 (year integers); row 0 has section labels
    hi = None
    # Year headers are ints in some quarters and strings ('2026') in others --
    # from 2024Q3 on, at least one block is text, which the old int-only test
    # missed, so no ramp change was parsed after 2024Q2.
    def header_year(c):
        m = re.fullmatch(r'(\d{4})', str(c).strip()) if c is not None else None
        yr = int(m.group(1)) if m else None
        return yr if yr is not None and 2020 <= yr <= 2040 else None

    for i, row in enumerate(rows):
        if any(header_year(c) for c in row):
            hi = i
            break
    if hi is None:
        return []

    # Identify which columns are year columns in the first block (new ramp)
    # and second block (prev ramp)
    year_new, year_prev = {}, {}
    seen_years = set()
    for ci, h in enumerate(rows[hi]):
        yr = header_year(h)
        if yr:
            if yr not in seen_years:
                year_new[ci] = yr
                seen_years.add(yr)
            elif yr not in {v for v in year_prev.values()}:
                year_prev[ci] = yr

    if not year_new or not year_prev:
        return []

    base = name_base(rows[hi])
    result = []
    for row in rows[hi + 1:]:
        if not is_project_row(row, base):
            continue
        new_ramp  = {yr: _num(row[ci]) for ci, yr in year_new.items() if ci < len(row)}
        prev_ramp = {yr: _num(row[ci]) for ci, yr in year_prev.items() if ci < len(row)}
        if any(v != 0 for v in new_ramp.values()) or any(v != 0 for v in prev_ramp.values()):
            result.append((prev_ramp, new_ramp))
    return result


def _num(v):
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_excel_stage_changes(ws):
    """Return list of (prev_stage, new_stage). Columns: name, current, previous."""
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    base = name_base(rows[hi])
    result = []
    for row in rows[hi + 1:]:
        if base + 2 >= len(row) or not is_project_row(row, base):
            continue
        new_stage, prev_stage = norm_stage(row[base + 1]), norm_stage(row[base + 2])
        if new_stage and prev_stage:
            result.append((prev_stage, new_stage))
    return result


def parse_excel_added(ws):
    """Return the announced loads listed on the Projects Added sheet."""
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    base = name_base(rows[hi])
    loads = []
    for row in rows[hi + 1:]:
        if base + 1 >= len(row) or not is_project_row(row, base):
            continue
        load = norm_load(row[base + 1])
        if load is not None:
            loads.append(load)
    return loads


def parse_excel_removed(ws):
    """Return list of (prev_announced_load, reason)."""
    rows = load_ws_rows(ws)
    hi = find_header_row(rows)
    if hi is None:
        return []
    base = name_base(rows[hi])
    result = []
    for row in rows[hi + 1:]:
        if base + 1 >= len(row) or not is_project_row(row, base):
            continue
        load   = norm_load(row[base + 1])
        reason = (str(row[base + 2]).strip()
                  if len(row) > base + 2 and row[base + 2] else "")
        if load is not None:
            result.append((load, reason))
    return result


# ── Similarity ────────────────────────────────────────────────────────────────

def ramp_sim(ramp1, ramp2):
    """Cosine similarity * magnitude ratio over the years both ramps report.

    The magnitude penalty ensures that flat ramps of different scales
    (e.g. 110 MW vs 180 MW) don't score 1.0 just because they're proportional.
    """
    years = [yr for yr in LOAD_YEARS if yr in ramp1 and yr in ramp2]
    v1 = np.array([float(ramp1[yr]) for yr in years])
    v2 = np.array([float(ramp2[yr]) for yr in years])
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 1.0 if n1 == n2 else 0.0
    cosine    = float(np.dot(v1, v2) / (n1 * n2))
    mag_ratio = min(n1, n2) / max(n1, n2)
    return cosine * mag_ratio

def ramp_equal(ramp1, ramp2, tol=0.5):
    """Same ramp in every year both report. Early filings carry 2023-2024
    columns that later ones dropped, so only the overlap is compared."""
    years = [yr for yr in LOAD_YEARS if yr in ramp1 and yr in ramp2]
    return bool(years) and all(abs(ramp1[yr] - ramp2[yr]) < tol for yr in years)


# ── Core matching: one min-cost assignment per quarter ────────────────────────
#
# Each filing is internally consistent: in every quarter,
#     prev_count - |Removed Projects| + |New Project? = Y| == current_count
# (2026Q1 and 2026Q3 are each off by one on the same 216 MW project: Q1's Main
# sheet omits its new flag though Projects Added lists it; Q3 flags it new
# again though Projects Added does not). So matching is a 1:1 assignment between last quarter's
# projects and this quarter's, where each project's own change flags say which
# attributes may differ, and the change sheets say what they used to be.
#
# Rows    = previous-quarter projects   + one "new project" slot per current project
#           + filler rows for unused removal slots
# Columns = current-quarter projects    + one slot per Removed Projects entry
#           + one "vanished, unexplained" slot per previous project
#
# Costs are additive penalties for evidence that contradicts a pairing:

W_LOAD      = 3.0   # announced load disagrees with flag / Load Change sheet
W_DATE      = 3.0   # in-service date disagrees with flag / Initial Service Change
W_STAGE     = 3.0   # stage disagrees with flag / Stage Change sheet
W_TERRITORY = 3.0   # Inside/Outside should never change
W_SEGMENT   = 1.0   # segment taxonomy has shifted between filings
W_CLASS     = 0.5
W_RAMP      = 1.0   # plus up to 1.0 more for ramp dissimilarity
W_UNEXPLAINED = 0.5 # flagged as changed, but the change sheet has no matching row
COST_NEW_FLAGGED    = 0.0  # current project flagged new, assigned a new ID
COST_NEW_UNFLAGGED  = 8.0  # current project NOT flagged new, assigned a new ID
COST_MATCH_FLAGGED  = 6.0  # continuing a project that the filing flags as new
COST_MATCH_FLAGGED_NOT_ADDED = 2.0  # ...and that is missing from Projects Added
COST_REMOVED_OK     = 0.0  # prev project -> Removed slot with the same load
COST_REMOVED_MISS   = 5.0  # prev project -> Removed slot with a different load
COST_VANISH         = 8.0  # prev project disappears without a Removed entry
INF = 1e6


def _attr_cost(prev_val, cur_val, flagged, pairs, weight):
    """Penalty for pairing a previous value with a current one.

    Unflagged attributes must be unchanged. Flagged attributes must have
    changed, to a previous value the change sheet lists for this current value.
    """
    if prev_val in (None, "") or cur_val in (None, ""):
        return 0.0
    if not flagged:
        return 0.0 if prev_val == cur_val else weight
    prevs = {p for p, n in pairs if n == cur_val}
    if prevs:
        return 0.0 if prev_val in prevs else weight
    return W_UNEXPLAINED if prev_val != cur_val else weight


def _ramp_cost(prev_ramp, cur_ramp, flagged, ramp_pairs):
    sim_pen = 1.0 - max(0.0, ramp_sim(prev_ramp, cur_ramp))
    if not flagged:
        return 0.0 if ramp_equal(prev_ramp, cur_ramp) else W_RAMP + sim_pen
    prevs = [pr for pr, nr in ramp_pairs if ramp_equal(nr, cur_ramp)]
    if prevs:
        if any(ramp_equal(prev_ramp, pr) for pr in prevs):
            return 0.0
        return W_RAMP + sim_pen
    # Flagged, but no ramp-change row to check against (or the sheet is absent).
    return (W_RAMP if ramp_equal(prev_ramp, cur_ramp) else 0.0) + 0.5 * sim_pen


def pair_cost(prev, cur, sheets):
    """Total penalty for continuing `prev` (last quarter's record) as `cur`."""
    c = 0.0
    c += _attr_cost(prev['announced_load'], cur['announced_load'],
                    cur['change_announced_load'] == 'Y', sheets['load'], W_LOAD)
    c += _attr_cost(prev['initial_service_date'], cur['initial_service_date'],
                    cur['change_initial_service_date'] == 'Y', sheets['date'], W_DATE)
    c += _attr_cost(prev['project_stage'], cur['project_stage'],
                    cur['change_project_stage'] == 'Y', sheets['stage'], W_STAGE)
    c += _ramp_cost(prev['ramp'], cur['ramp'],
                    cur['change_load_ramp'] == 'Y', sheets['ramp'])
    if prev['territory'] and cur['territory'] and \
            prev['territory'].lower() != cur['territory'].lower():
        c += W_TERRITORY
    if prev['segment'] and cur['segment'] and prev['segment'] != cur['segment']:
        c += W_SEGMENT
    if prev['class_type'] and cur['class_type'] and \
            prev['class_type'].lower() != cur['class_type'].lower():
        c += W_CLASS
    if cur['new_project'] == 'Y':
        added = sheets.get('added')
        not_listed = added is not None and cur['announced_load'] not in added
        c += COST_MATCH_FLAGGED_NOT_ADDED if not_listed else COST_MATCH_FLAGGED
    return c


def confidence_label(cost):
    if cost == 0:
        return 'exact'      # every attribute reconciles with the filing
    if cost < W_LOAD:
        return 'high'       # minor disagreement (segment relabel, unlisted change)
    return 'low'            # a substantive attribute disagrees


def match_quarter(prev_pids, prev_master, current, sheets):
    """Assign each current project to a previous project or to 'new'.

    Returns (assignment, costs, outcome) where assignment[i] is a previous
    proj_id or None, costs[i] the pairing cost, and outcome summarizes how the
    previous projects were accounted for.
    """
    from scipy.optimize import linear_sum_assignment

    prev = [prev_master[pid] for pid in prev_pids]
    m, n = len(prev), len(current)
    removed = [load for load, _ in sheets['removed']]
    r = len(removed)
    size = m + n + r
    C = np.full((size, size), INF)

    # Small order-preserving tiebreak: filings list projects in a stable order,
    # so among otherwise identical candidates prefer the same relative position.
    def order_eps(i, j):
        return 1e-4 * abs(i / max(m, 1) - j / max(n, 1))

    for i, p in enumerate(prev):
        for j, cur in enumerate(current):
            C[i, j] = pair_cost(p, cur, sheets) + order_eps(i, j)
        for k, load in enumerate(removed):
            C[i, n + k] = COST_REMOVED_OK if p['announced_load'] == load else COST_REMOVED_MISS
        C[i, n + r:] = COST_VANISH
    for j, cur in enumerate(current):
        C[m + j, j] = COST_NEW_FLAGGED if cur['new_project'] == 'Y' else COST_NEW_UNFLAGGED
        C[m + j, n:] = 0.0            # unused new-slot rows soak up spare columns
    C[m + n:, n:] = 0.0               # filler rows soak up unused removal / vanish slots

    rows, cols = linear_sum_assignment(C)
    assignment, costs = [None] * n, [0.0] * n
    outcome = {'removed_ok': 0, 'removed_miss': 0, 'vanished': 0}
    for i, j in zip(rows, cols):
        if i < m and j < n:
            assignment[j] = prev_pids[i]
            costs[j] = round(C[i, j] - order_eps(i, j), 6)
        elif i < m and j < n + r:
            outcome['removed_ok' if C[i, j] == COST_REMOVED_OK else 'removed_miss'] += 1
        elif i < m:
            outcome['vanished'] += 1
    return assignment, costs, outcome


# ── Load one quarter's inputs ─────────────────────────────────────────────────

def load_excel_quarter(quarter):
    qdir = WORKBOOKS_DIR / quarter
    xlsxs = list(qdir.glob("*.xlsx")) if qdir.exists() else []
    if not xlsxs:
        return None, None
    wb = openpyxl.load_workbook(xlsxs[0], read_only=True, data_only=True)
    sheet = {s.lower(): s for s in wb.sheetnames}

    def get(name, parser, default):
        return parser(wb[sheet[name]]) if name in sheet else default

    projects = get('main', lambda ws: parse_excel_main(ws, quarter), [])
    sheets = {
        'load':    get('load change', parse_excel_load_changes, []),
        'date':    get('initial service change', parse_excel_date_changes, []),
        'ramp':    get('ramp change', parse_excel_ramp_changes, []),
        'stage':   get('stage change', parse_excel_stage_changes, []),
        'removed': get('removed projects', parse_excel_removed, []),
        'added':   get('projects added', parse_excel_added, None),
    }
    return projects, sheets


# ── Main ──────────────────────────────────────────────────────────────────────

def _record(proj):
    return {k: proj[k] for k in ('segment', 'class_type', 'territory', 'project_stage',
                                 'announced_load', 'initial_service_date', 'ramp')}


def _row(pid, quarter, first_seen, conf, proj):
    row = {
        'proj_id': pid, 'report_quarter': quarter,
        'quarter_first_seen': first_seen, 'match_confidence': conf,
        'segment': proj['segment'], 'class_type': proj['class_type'],
        'territory': proj['territory'], 'project_stage': proj['project_stage'],
        'announced_load_mw': proj['announced_load'],
        'initial_service_date': proj['initial_service_date'],
        'new_project': proj['new_project'],
        'change_announced_load': proj['change_announced_load'],
        'change_load_ramp': proj['change_load_ramp'],
        'change_project_stage': proj['change_project_stage'],
        'change_initial_service_date': proj['change_initial_service_date'],
    }
    for yr in LOAD_YEARS:
        row[f'load_{yr}'] = proj['ramp'].get(yr) if yr in proj['ramp'] else None
    return row


def main():
    COMBINED_DIR.mkdir(parents=True, exist_ok=True)

    master = {}        # {proj_id: last-seen record}
    first_seen = {}    # {proj_id: quarter}
    prev_pids = []     # proj_ids present in the previous quarter, in filing order
    next_id = 1
    all_rows = []
    summary = []

    for quarter in QUARTER_ORDER:
        print(f"\n[{quarter}]")
        projects, sheets = load_excel_quarter(quarter)
        if projects is None:
            print("  Skipping — no workbook found")
            continue

        flagged = sum(p['new_project'] == 'Y' for p in projects)
        print(f"  {len(projects)} projects in Main sheet ({flagged} flagged new)")
        print(f"  change sheets: {len(sheets['load'])} load, {len(sheets['date'])} date, "
              f"{len(sheets['ramp'])} ramp, {len(sheets['stage'])} stage, "
              f"{len(sheets['removed'])} removed")

        if not prev_pids:
            assignment, costs = [None] * len(projects), [0.0] * len(projects)
            outcome = {}
        else:
            expected = len(prev_pids) - len(sheets['removed']) + flagged
            if expected != len(projects):
                print(f"  NOTE: filing does not reconcile: {len(prev_pids)} prev "
                      f"- {len(sheets['removed'])} removed + {flagged} flagged new "
                      f"= {expected}, but Main has {len(projects)}")
            assignment, costs, outcome = match_quarter(prev_pids, master, projects, sheets)

        rows_q, pids_q = [], []
        counts = {'seed': 0, 'new': 0, 'exact': 0, 'high': 0, 'low': 0}
        overrides = 0
        for proj, pid, cost in zip(projects, assignment, costs):
            if pid is None:
                pid = f"P{next_id:04d}"
                next_id += 1
                first_seen[pid] = quarter
                conf = 'seed' if not prev_pids else 'new'
                if conf == 'new' and proj['new_project'] != 'Y':
                    overrides += 1
            else:
                conf = confidence_label(cost)
                if proj['new_project'] == 'Y':
                    overrides += 1
            counts[conf] += 1
            master[pid] = _record(proj)
            pids_q.append(pid)
            rows_q.append(_row(pid, quarter, first_seen[pid], conf, proj))

        all_rows.extend(rows_q)
        prev_pids = pids_q
        print(f"  Match summary: {counts}")
        if outcome:
            print(f"  Previous projects: {outcome['removed_ok']} removed (load matches sheet), "
                  f"{outcome['removed_miss']} removed (load mismatch), "
                  f"{outcome['vanished']} vanished unexplained")
        if overrides:
            print(f"  NOTE: {overrides} project(s) assigned against their New Project? flag")
        summary.append((quarter, len(projects), counts, outcome, overrides))

    # Output
    df = pd.DataFrame(all_rows)

    # project_age: number of quarters this project has appeared in the pipeline
    df = df.sort_values(['proj_id', 'report_quarter'])
    df['project_age'] = df.groupby('proj_id').cumcount() + 1

    id_cols = ['proj_id', 'report_quarter', 'quarter_first_seen', 'project_age', 'match_confidence']
    attr_cols = ['segment', 'class_type', 'territory', 'project_stage',
                 'announced_load_mw', 'initial_service_date']
    flag_cols = ['new_project', 'change_announced_load', 'change_load_ramp',
                 'change_project_stage', 'change_initial_service_date']
    yr_cols = [f'load_{yr}' for yr in LOAD_YEARS]
    df = df[id_cols + attr_cols + flag_cols + yr_cols]

    out = COMBINED_DIR / "pipeline_projects.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {out}")
    print(f"  {len(df)} total rows, {df['proj_id'].nunique()} unique project IDs")

    print("\n--- Per-quarter summary ---")
    print(f"{'Quarter':<9} {'Projects':>8} {'New':>5} {'Exact':>6} {'High':>5} {'Low':>5} "
          f"{'Removed':>8} {'RemMiss':>8} {'Vanish':>7} {'FlagOvr':>8}")
    print("-" * 80)
    for q, n, c, o, ovr in summary:
        print(f"{q:<9} {n:>8} {c['new'] + c['seed']:>5} {c['exact']:>6} {c['high']:>5} "
              f"{c['low']:>5} {o.get('removed_ok', 0):>8} {o.get('removed_miss', 0):>8} "
              f"{o.get('vanished', 0):>7} {ovr:>8}")


if __name__ == "__main__":
    main()
