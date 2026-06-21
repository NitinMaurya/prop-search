"""Streamlit UI — requirement form + matches dashboard + System/Status + Settings.

See docs/ARCHITECTURE.md. Four pages (sidebar nav): Requirements, Matches, System,
and Settings (live matcher tuning knobs from the DB, D17). Presentation is custom-styled
(CSS in _inject_css); all data flows through db.py's public functions only.

  1. Requirements (D9): full CRUD — create / list / EDIT / deactivate. User data, never
     hardcoded; the scheduler loops every active row.
  2. Matches (D5/D6): ranked match cards with score badge + clickable listing link.
  3. System/Status (D15): per-portal status, pipeline health, parse errors, run history.
  4. Settings (D17): live matcher knobs stored in the DB.

Run: streamlit run app.py
"""

import ast
import html
import os
from collections import Counter
import re
import subprocess
import sys
import urllib.parse

import streamlit as st

import db
import matcher
import property_types as pt

_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def run_scrape_now() -> tuple[bool, str]:
    """Run one pipeline cycle on demand via `scheduler.py --once` (subprocess, so
    Playwright runs outside Streamlit's thread). Returns (ok, human summary)."""
    try:
        proc = subprocess.run(
            [sys.executable, "scheduler.py", "--once"],
            cwd=_APP_DIR, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "Scrape timed out after 10 minutes."
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"run \d+ done: (\{.*\})", out)
    if proc.returncode == 0 and m:
        try:
            return True, ast.literal_eval(m.group(1))  # structured stats dict
        except (ValueError, SyntaxError):
            return True, {}
    if proc.returncode == 0:
        return True, {}
    tail = "\n".join(out.strip().splitlines()[-3:])
    return False, f"Scrape failed (exit {proc.returncode}).\n{tail}"


def start_scrape_bg() -> None:
    """Launch the scrape in the BACKGROUND (non-blocking) so the app stays interactive
    while it runs. Output goes to the log file (not a pipe — a pipe could fill its buffer
    and deadlock a multi-minute scrape); results are read back from the DB on completion."""
    import streamlit as _st
    logf = open(os.path.join(_APP_DIR, "logs", "scheduler.log"), "a")
    proc = subprocess.Popen(
        [sys.executable, "scheduler.py", "--once"], cwd=_APP_DIR,
        stdout=logf, stderr=subprocess.STDOUT)
    _st.session_state["scrape_proc"] = proc


def finish_scrape_bg(proc) -> tuple[bool, dict | str]:
    """Build the result of a finished background scrape from the latest DB run row."""
    rc = proc.returncode
    if rc != 0:
        return False, f"Scrape failed (exit {rc}). See logs/scheduler.log."
    runs = db.recent_runs(1)
    r = runs[0] if runs else {}
    return True, {
        "raw_fetched": r.get("raw_fetched", 0),
        "parsed_ok": r.get("parsed_ok", 0),
        "parse_errors": r.get("parse_errors", 0),
        "new_matches": r.get("new_matches", 0),
        "notified": r.get("notified", 0),
        "portals_run": len(db.list_enabled_portals()),
    }


def _relative_time(iso: str | None) -> str | None:
    """'3 minutes ago' style relative time from an ISO timestamp (None if unparseable)."""
    if not iso:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    secs = (now - dt).total_seconds()
    if secs < 0:
        secs = 0
    if secs < 60:
        return "just now"
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if secs >= n:
            v = int(secs // n)
            return f"{v} {unit}{'s' if v != 1 else ''} ago"
    return "just now"


CR = 10_000_000  # 1 Crore = 10,000,000 rupees (D9 budget display convenience)
SIZE_OPTIONS = [112, 162]  # confirmed target sizes (Q2); custom allowed via number input
_TYPE_SHORT = {"house": "Kothi", "plot": "Plot", "apartment": "Flat"}


def _requirement_summary(r: dict) -> str:
    """Short human label for a requirement, e.g. 'nitin · Kothi · 112/162 sqm · ₹3–5 Cr'."""
    parts = []
    if r.get("owner"):
        parts.append(r["owner"])
    parts.append(_TYPE_SHORT.get(pt.category_of(r.get("property_type")), "Home"))
    sizes = r.get("sizes_sqm") or []
    if sizes:
        parts.append("/".join(str(int(s)) for s in sizes) + " sqm")
    if r.get("budget_max"):
        parts.append(f"₹{rupees_to_cr(r.get('budget_min')):g}–"
                     f"{rupees_to_cr(r['budget_max']):g} Cr")
    return " · ".join(parts)


def rupees_to_cr(rupees) -> float:
    return round((rupees or 0) / CR, 4)


def cr_to_rupees(cr) -> int:
    return int(round((cr or 0) * CR))


# ------------------------------------------------------------------------- page styling
def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ps-bg:#d6dce8; --ps-surface:#ffffff; --ps-ink:#0f172a;
            --ps-muted:#64748b; --ps-line:#dfe3ec; --ps-line2:#eef0f6;
            --ps-brand:#4f46e5; --ps-brand-dk:#4338ca; --ps-brand-soft:#eef2ff;
            --ps-brand2:#8b5cf6;  /* violet — second stop of the brand gradient */
            --ps-grad:linear-gradient(135deg,#6366f1 0%,#8b5cf6 100%);
            --ps-shadow:0 1px 2px rgba(16,24,40,.05), 0 10px 26px -12px rgba(16,24,40,.16);
            --ps-shadow-hi:0 6px 16px -6px rgba(99,102,241,.18),
                0 22px 48px -18px rgba(124,58,237,.36);
        }
        html, body, [class*="css"] {-webkit-font-smoothing:antialiased;}
        /* ---- never scroll the page sideways (hard requirement) ---- */
        html, body {max-width:100%; overflow-x:hidden;}
        /* cool slate canvas + a faint indigo/violet "aurora" up top for modern depth */
        .stApp {background:
            radial-gradient(1100px 460px at 50% -8%, rgba(124,58,237,.14), transparent 62%) fixed,
            radial-gradient(900px 360px at 88% 2%, rgba(79,70,229,.10), transparent 60%) fixed,
            linear-gradient(180deg,#e4e8f2 0%, var(--ps-bg) 52%) fixed;
            max-width:100%; overflow-x:hidden;}
        *, *::before, *::after {box-sizing:border-box;}
        /* keep every Streamlit block/column within its track, never wider */
        [data-testid="stAppViewContainer"], [data-testid="stMain"],
        .main, .block-container {max-width:100%; overflow-x:hidden;}
        [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"],
        [data-testid="column"] {min-width:0; max-width:100%;}
        /* media + interactive elements may never exceed their container */
        img, video, canvas, iframe, svg {max-width:100%; height:auto;}
        .stButton > button, .stFormSubmitButton > button {max-width:100%;}
        /* long unbreakable tokens (urls, titles, sectors) must wrap, not push width */
        p, span, a, h1, h2, h3, h4, li, td, th, .stMarkdown {
            overflow-wrap:anywhere; word-break:break-word;}
        .block-container {padding-top: 1.4rem; padding-bottom: 1.5rem; max-width: 100%;
            padding-left: 2.6rem; padding-right: 2.6rem;}
        /* hide Streamlit chrome; the hover icon-rail replaces the collapse/expand UI */
        #MainMenu, footer, header[data-testid="stHeader"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {display:none !important;}

        /* ---- page header ---- */
        .ps-h1 {font-size: 1.9rem; font-weight: 800; margin: 0 0 .15rem;
            color:var(--ps-ink); letter-spacing:-.02em;}
        .ps-sub {color:var(--ps-muted); font-size:.97rem; margin: 0 0 1rem;
            max-width:62ch;}
        .ps-section {font-size:.78rem; font-weight:750; letter-spacing:.08em;
            text-transform:uppercase; color:var(--ps-muted); margin:1.6rem 0 .7rem;}

        /* ---- streamlit subheaders harmonised ---- */
        [data-testid="stHeadingWithActionElements"] h3 {font-size:1.05rem;
            font-weight:750; color:var(--ps-ink); letter-spacing:-.01em;}

        /* ---- metric tiles ---- */
        div[data-testid="stMetric"] {background:var(--ps-surface);
            border:1px solid var(--ps-line); border-radius:16px; padding:16px 20px;
            box-shadow:var(--ps-shadow);}
        div[data-testid="stMetricLabel"] p {font-size:.8rem; font-weight:650;
            color:var(--ps-muted); letter-spacing:.01em;}
        div[data-testid="stMetricValue"] {font-size:1.7rem; font-weight:800;
            letter-spacing:-.02em; color:var(--ps-ink);}

        /* ---- inputs ---- */
        div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {
            border-radius:11px !important; border-color:var(--ps-line) !important;}
        .stTextInput input:focus, .stNumberInput input:focus {
            border-color:var(--ps-brand) !important;}

        /* ---- buttons ---- */
        .stButton > button, .stFormSubmitButton > button {border-radius:11px;
            font-weight:650; border:1px solid var(--ps-line); transition:all .15s ease;}
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"]{
            background:var(--ps-grad) !important; border:none !important; color:#fff !important;
            box-shadow:0 8px 20px -8px rgba(124,58,237,.6);}
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {transform:translateY(-1px);
            box-shadow:0 12px 26px -8px rgba(124,58,237,.7);}

        /* ---- expanders ---- */
        [data-testid="stExpander"] {border:1px solid var(--ps-line);
            border-radius:14px; background:var(--ps-surface); box-shadow:var(--ps-shadow);}

        /* ---- dialog/modal: a medium width (Streamlit only ships small/large) ---- */
        div[data-testid="stDialog"] div[role="dialog"] {width:600px !important;
            max-width:92vw !important;}

        /* follow-up rows → elevated white cards */
        [class*="st-key-followcard"] {
            background:var(--ps-surface); border:1px solid var(--ps-line) !important;
            border-radius:16px; box-shadow:var(--ps-shadow); margin-bottom:14px;
            padding:14px 20px !important;
            transition:box-shadow .18s ease, border-color .18s ease;}
        [class*="st-key-followcard"]:hover {
            box-shadow:var(--ps-shadow-hi); border-color:#c4cbe0 !important;}

        /* ---- requirements table ---- */
        [class*="st-key-reqtable"] {background:var(--ps-surface);
            border:1px solid var(--ps-line) !important; border-radius:16px;
            box-shadow:var(--ps-shadow); padding:0 24px !important; overflow:hidden;}
        /* each st.columns row is a horizontal block */
        [class*="st-key-reqtable"] [data-testid="stHorizontalBlock"] {
            border-bottom:1px solid var(--ps-line2); padding:16px 0; align-items:center;
            min-height:0;}
        [class*="st-key-reqtable"] [data-testid="stHorizontalBlock"]:last-child {
            border-bottom:none;}
        /* header row: generous padding + a strong divider (no full-bleed tint — it left a
           gap on the right; bold headers read clearly on their own) */
        [class*="st-key-reqtable"] [data-testid="stHorizontalBlock"]:first-child {
            padding:18px 0 14px; border-bottom:2px solid var(--ps-line);}
        .ps-th {font-size:1.02rem; font-weight:800; letter-spacing:-.01em;
            color:var(--ps-ink);}
        .ps-td {font-size:.92rem; font-weight:600; color:#334155; overflow-wrap:anywhere;}
        .ps-td-strong {font-weight:800; color:var(--ps-ink); font-size:.98rem;}
        .ps-stat {font-size:.72rem; font-weight:750; padding:3px 10px; border-radius:999px;
            white-space:nowrap;}
        .ps-stat-on {background:#dcfce7; color:#15803d;}
        .ps-stat-off {background:#f1f5f9; color:#64748b;}
        /* compact edit button in the table */
        [class*="st-key-reqtable"] .stButton > button {padding:4px 0; min-height:36px;}

        /* ============================== System page ============================== */
        /* stat tiles — compact, with optional semantic accent bar */
        .ps-tilerow {display:flex; flex-wrap:wrap; gap:14px; margin:.2rem 0 0;}
        .ps-tile {flex:1 1 150px; min-width:0; background:var(--ps-surface);
            border:1px solid var(--ps-line); border-radius:16px; padding:14px 18px;
            box-shadow:var(--ps-shadow); position:relative; overflow:hidden;}
        .ps-tile::before {content:""; position:absolute; left:0; top:0; bottom:0;
            width:4px; background:var(--ps-grad);}
        .ps-tile.ps-tile-warn::before {background:linear-gradient(180deg,#f59e0b,#f97316);}
        .ps-tile.ps-tile-bad::before {background:linear-gradient(180deg,#ef4444,#dc2626);}
        .ps-tile.ps-tile-ok::before {background:linear-gradient(180deg,#22c55e,#16a34a);}
        .ps-tile-lbl {font-size:.74rem; font-weight:650; color:var(--ps-muted);
            letter-spacing:.02em; margin-bottom:.25rem; overflow-wrap:anywhere;}
        .ps-tile-val {font-size:1.7rem; font-weight:850; letter-spacing:-.02em;
            color:var(--ps-ink); line-height:1;}
        .ps-tile-val.ps-v-warn {color:#b45309;}
        .ps-tile-val.ps-v-bad {color:#b91c1c;}
        .ps-tile-val.ps-v-ok {color:#15803d;}

        /* portal cards */
        .ps-portalrow {display:flex; flex-wrap:wrap; gap:14px; margin-top:.2rem;}
        .ps-portal {flex:1 1 220px; min-width:0; background:var(--ps-surface);
            border:1px solid var(--ps-line); border-radius:16px; padding:14px 18px;
            box-shadow:var(--ps-shadow);}
        .ps-portal-head {display:flex; align-items:center; justify-content:space-between;
            gap:10px; flex-wrap:wrap;}
        .ps-portal-name {font-weight:800; color:var(--ps-ink); font-size:1rem;
            overflow-wrap:anywhere;}
        .ps-portal-meta {font-size:.78rem; color:var(--ps-muted); font-weight:600;
            margin-top:.5rem; overflow-wrap:anywhere;}
        .ps-portal-meta b {color:#334155; font-weight:700;}

        /* run-history table (reuses reqtable shell + ps-th/ps-td) */
        [class*="st-key-runtable"] {background:var(--ps-surface);
            border:1px solid var(--ps-line) !important; border-radius:16px;
            box-shadow:var(--ps-shadow); padding:0 22px !important; overflow:hidden;}
        [class*="st-key-runtable"] [data-testid="stHorizontalBlock"] {
            border-bottom:1px solid var(--ps-line2); padding:11px 0; align-items:center;
            min-height:0;}
        [class*="st-key-runtable"] [data-testid="stHorizontalBlock"]:last-child {
            border-bottom:none;}
        [class*="st-key-runtable"] [data-testid="stHorizontalBlock"]:first-child {
            padding:15px 0 11px; border-bottom:2px solid var(--ps-line);}
        .ps-th-c {font-size:.74rem; font-weight:800; letter-spacing:.04em;
            text-transform:uppercase; color:#64748b;}
        .ps-td-c {font-size:.86rem; font-weight:600; color:#334155;
            overflow-wrap:anywhere;}
        .ps-td-c.ps-td-mut {color:#94a3b8; font-weight:600;}
        .ps-num-bad {color:#b91c1c; font-weight:800;}
        .ps-num-zero {color:#94a3b8; font-weight:600;}

        /* parse-error list */
        .ps-errlist {display:flex; flex-direction:column; gap:10px; margin-top:.2rem;}
        .ps-err {background:var(--ps-surface); border:1px solid var(--ps-line);
            border-left:4px solid #ef4444; border-radius:12px; padding:11px 16px;
            box-shadow:var(--ps-shadow); min-width:0; max-width:100%;}
        .ps-err-url {font-size:.82rem; font-weight:700; color:var(--ps-ink);
            overflow-wrap:anywhere; word-break:break-word;}
        .ps-err-msg {font-size:.8rem; color:#b91c1c; font-weight:600; margin-top:.2rem;
            overflow-wrap:anywhere; word-break:break-word;}
        .ps-ok-state {background:#ecfdf5; border:1px solid #a7f3d0; border-radius:14px;
            padding:14px 18px; color:#15803d; font-weight:700; font-size:.92rem;
            box-shadow:var(--ps-shadow);}

        /* ---- view segmented toggle: right-align beside the heading ---- */
        /* the View toggle's element-container is width:fit-content, so it hugs the left;
           force it full-width and push the button group to the right edge */
        .st-key-match_view {width:100% !important; display:flex !important;
            justify-content:flex-end !important;}
        .st-key-match_view [data-testid="stButtonGroup"] {margin-left:auto !important;}
        [data-testid="stSegmentedControl"] {display:flex; justify-content:flex-end;
            width:100% !important;}
        [data-testid="stSegmentedControl"] [role="radiogroup"],
        [data-testid="stSegmentedControl"] > div {justify-content:flex-end;
            margin-right:0 !important;}

        /* ---- match card grid ---- */
        /* minmax(min(100%,300px),1fr): a single card can go full-width on narrow
           viewports rather than forcing horizontal overflow. */
        .ps-grid {display:grid;
            grid-template-columns:repeat(auto-fill, minmax(min(100%, 300px), 1fr));
            gap:18px; margin-top:.3rem; max-width:100%;}
        .ps-card {position:relative; background:var(--ps-surface);
            border:1px solid var(--ps-line);
            border-radius:18px; overflow:hidden; box-shadow:var(--ps-shadow);
            display:flex; flex-direction:column; transition:transform .18s ease,
            box-shadow .18s ease; height:100%; min-width:0; max-width:100%;}
        .ps-card:hover {transform:translateY(-4px); box-shadow:var(--ps-shadow-hi);
            border-color:#dcd9fb;}
        .ps-photo {position:relative; aspect-ratio:16/10; background:
            linear-gradient(135deg,#eef2ff,#e0e7ff); overflow:hidden;}
        .ps-photo img {width:100%; height:100%; object-fit:cover; display:block;
            transition:transform .35s ease;}
        .ps-photo:hover img {transform:scale(1.12);}
        .ps-photo-ph {width:100%; height:100%; display:flex; align-items:center;
            justify-content:center; font-size:2.6rem; opacity:.55;}
        .ps-badge {position:absolute; top:12px; right:12px; border-radius:999px;
            padding:5px 12px; font-weight:800; font-size:.82rem; backdrop-filter:blur(6px);
            box-shadow:0 2px 8px rgba(16,24,40,.18); white-space:nowrap;}
        .ps-hi {background:rgba(220,252,231,.95); color:#15803d;}
        .ps-mid {background:rgba(254,249,195,.95); color:#a16207;}
        .ps-lo {background:rgba(241,245,249,.95); color:#475569;}
        .ps-sectortag {position:absolute; left:12px; bottom:12px; right:12px; z-index:3;
            max-width:calc(100% - 24px); background:rgba(15,23,42,.72);
            color:#fff !important; text-decoration:none !important; border-radius:8px;
            padding:4px 10px; font-size:.78rem; font-weight:650; backdrop-filter:blur(4px);
            overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
            display:flex; align-items:center; gap:6px; transition:background .12s ease;}
        .ps-sectortag:hover {background:rgba(37,99,235,.92);}
        .ps-map-ic {margin-left:auto; opacity:.9; font-size:.8rem;}
        .ps-desc {font-size:.83rem; color:var(--ps-muted); line-height:1.5;
            margin:0 0 .8rem; display:-webkit-box; -webkit-line-clamp:2;
            -webkit-box-orient:vertical; overflow:hidden; overflow-wrap:anywhere;}
        /* "new this run" tags */
        .ps-new-tag {position:absolute; top:10px; left:10px; z-index:3;
            background:linear-gradient(135deg,#10b981,#059669); color:#fff;
            font-size:.72rem; font-weight:800; letter-spacing:.02em; padding:4px 10px;
            border-radius:999px; box-shadow:0 2px 10px -2px rgba(5,150,105,.6);}
        .ps-new-pill {display:inline-block; background:#10b981; color:#fff;
            font-size:.62rem; font-weight:800; letter-spacing:.06em; padding:1px 6px;
            border-radius:6px; vertical-align:middle;}
        /* group-by-sector section headings */
        .ps-sec-group {margin:0 0 1.6rem;}
        .ps-sec-h {display:flex; align-items:center; gap:10px; font-size:1.1rem;
            font-weight:800; color:var(--ps-ink); letter-spacing:-.01em;
            margin:.4rem 0 .9rem; padding-bottom:.5rem;
            border-bottom:2px solid var(--ps-line);}
        .ps-sec-n {font-size:.72rem; font-weight:750; color:var(--ps-brand-dk);
            background:var(--ps-brand-soft); border-radius:999px; padding:2px 10px;}
        /* sector→maps link in the table sub-line (above the stretched row link) */
        .ps-tb-map {position:relative; z-index:2; text-decoration:none !important;
            color:var(--ps-brand-dk) !important; font-weight:700; white-space:nowrap;}
        .ps-tb-map:hover {text-decoration:underline !important;}
        /* lightbox description + map button */
        .ps-lb-desc {color:#e2e8f0; font-size:.9rem; line-height:1.55; margin:10px auto 0;
            max-width:60ch; text-align:center; max-height:5.5em; overflow:auto;}
        .ps-lb-map {background:rgba(255,255,255,.14) !important;}
        .ps-body {padding:16px 18px 18px; display:flex; flex-direction:column;
            flex:1 1 auto;}
        .ps-price {font-size:1.5rem; font-weight:850; color:var(--ps-ink);
            letter-spacing:-.02em; margin:0 0 .1rem; line-height:1;
            overflow-wrap:anywhere;}
        .ps-price small {font-size:.8rem; font-weight:650; color:var(--ps-muted);}
        .ps-title {font-size:.95rem; font-weight:600; color:#334155; line-height:1.4;
            margin:.5rem 0 .8rem; display:-webkit-box; -webkit-line-clamp:2;
            -webkit-box-orient:vertical; overflow:hidden; min-height:2.5em;
            overflow-wrap:anywhere; word-break:break-word;}
        .ps-chips {display:flex; flex-wrap:wrap; gap:7px; margin-bottom:1rem;
            min-width:0;}
        .ps-chip {background:var(--ps-brand-soft); color:var(--ps-brand-dk);
            border-radius:8px; padding:4px 10px; font-size:.78rem; font-weight:650;
            max-width:100%; overflow-wrap:anywhere; word-break:break-word;}
        .ps-chip-n {background:#f1f5f9; color:#475569;}
        .ps-card-foot {margin-top:auto; display:flex; align-items:center;
            justify-content:space-between; gap:10px; padding-top:.6rem;
            border-top:1px solid var(--ps-line2); flex-wrap:wrap; min-width:0;}
        .ps-meta {font-size:.74rem; color:var(--ps-muted); font-weight:600;
            min-width:0; overflow-wrap:anywhere; word-break:break-word;}
        .ps-btn {display:inline-block; background:var(--ps-brand); color:#fff !important;
            text-decoration:none; padding:8px 15px; border-radius:10px; font-weight:700;
            font-size:.82rem; transition:background .15s ease;}
        .ps-btn:hover {background:var(--ps-brand-dk);}

        /* ---- dataframe / table view: scroll INTERNALLY, never widen the page ---- */
        [data-testid="stDataFrame"], [data-testid="stDataFrameResizable"],
        [data-testid="stTable"] {max-width:100% !important; overflow-x:auto;}
        [data-testid="stDataFrame"] > div {max-width:100%;}

        /* ---- custom Matches table view ---- */
        .ps-table-wrap {width:100%; max-width:100%;}
        .ps-table {width:100%; max-width:100%; border-collapse:separate;
            border-spacing:0 8px; table-layout:fixed;}
        .ps-table th {text-align:left; font-size:.7rem; text-transform:uppercase;
            letter-spacing:.05em; color:#94a3b8; font-weight:800; padding:0 14px 2px;}
        .ps-th-sort {display:inline-flex; align-items:center; gap:5px; color:#94a3b8;
            text-decoration:none !important; cursor:pointer; transition:color .12s ease;}
        .ps-th-sort:hover {color:var(--ps-brand);}
        .ps-th-sort.active {color:var(--ps-brand);}
        .ps-th-arr {font-size:.7rem; opacity:.8;}
        .ps-table td {background:#fff; padding:11px 14px; vertical-align:middle;
            border-top:1px solid var(--ps-line); border-bottom:1px solid var(--ps-line);
            overflow-wrap:anywhere; word-break:break-word;}
        .ps-table td:first-child {border-left:1px solid var(--ps-line);
            border-radius:14px 0 0 14px;}
        .ps-table td:last-child {border-right:1px solid var(--ps-line);
            border-radius:0 14px 14px 0;}
        .ps-table tbody tr {box-shadow:0 1px 2px rgba(16,24,40,.04);
            transition:transform .12s ease, box-shadow .12s ease;}
        .ps-table tbody tr:hover {transform:translateY(-1px);
            box-shadow:0 6px 18px rgba(16,24,40,.09);}
        .ps-table tbody tr:hover td {background:#fcfcff;}
        .ps-tb-photo {width:56px; height:56px; border-radius:11px; object-fit:cover;
            display:block; max-width:100%; transition:transform .3s ease;
            transform-origin:center; cursor:zoom-in;}
        .ps-tb-photo:hover {transform:scale(1.5); position:relative; z-index:20;
            box-shadow:0 10px 30px rgba(16,24,40,.28);}
        .ps-tb-photo-ph {display:flex; align-items:center; justify-content:center;
            font-size:1.4rem; background:linear-gradient(135deg,#eef2ff,#e0e7ff);}
        .ps-tb-title {font-weight:680; color:var(--ps-ink); line-height:1.3;
            font-size:.95rem;}
        .ps-tb-sub {color:#64748b; font-size:.8rem; margin-top:3px; line-height:1.35;}
        .ps-tb-size {color:#334155; font-weight:600; font-size:.9rem;}
        .ps-tb-size small, .ps-tb-price small {color:#94a3b8; font-weight:600;}
        .ps-tb-price {color:var(--ps-brand); font-weight:850; font-size:1.05rem;
            white-space:nowrap;}
        .ps-tb-score {display:flex; align-items:center; gap:9px;}
        .ps-tb-bar {flex:1; min-width:0; height:7px; border-radius:999px;
            background:#eef1f6; overflow:hidden;}
        .ps-tb-bar > i {display:block; height:100%; border-radius:999px;}
        .ps-tb-pct {font-size:.82rem; font-weight:800; color:#475569; min-width:34px;
            text-align:right;}
        .ps-tb-act {text-align:right;}
        .ps-tb-open {display:inline-block; background:var(--ps-brand); color:#fff !important;
            text-decoration:none; padding:7px 14px; border-radius:9px; font-weight:700;
            font-size:.82rem; white-space:nowrap; max-width:100%;}
        .ps-tb-open:hover {background:var(--ps-brand-dk);}
        .ps-tb-nolink {color:#cbd5e1;}

        /* ---- lightbox gallery (pure CSS, :target) ---- */
        .ps-zoom {display:block; width:100%; height:100%; cursor:zoom-in;}
        .ps-lb {position:fixed; inset:0; z-index:99999; display:none;}
        .ps-lb:target {display:block;}
        .ps-lb-backdrop {position:absolute; inset:0; background:rgba(8,11,20,.93);
            backdrop-filter:blur(5px); cursor:zoom-out;}
        .ps-lb-stage {position:absolute; inset:0; display:flex; flex-direction:column;
            align-items:center; justify-content:center; padding:2vh 1vw;
            pointer-events:none;}
        .ps-lb-img {max-width:97vw; max-height:90vh; object-fit:contain;
            border-radius:10px; box-shadow:0 30px 80px rgba(0,0,0,.6); pointer-events:none;}
        .ps-lb-cap {margin-top:16px; color:#e5e7eb; font-size:.95rem; font-weight:600;
            text-align:center; max-width:84vw; overflow-wrap:anywhere;}
        .ps-lb-count {display:block; color:#94a3b8; font-size:.82rem; font-weight:700;
            margin-top:4px;}
        .ps-lb-close, .ps-lb-nav {position:absolute; z-index:5; color:#fff;
            text-decoration:none; display:flex; align-items:center; justify-content:center;
            background:rgba(255,255,255,.14); border-radius:999px; font-weight:700;
            transition:background .15s ease;}
        .ps-lb-close:hover, .ps-lb-nav:hover {background:rgba(255,255,255,.28);}
        .ps-lb-close {top:3vh; right:3vw; width:46px; height:46px; font-size:1.25rem;}
        .ps-lb-nav {top:50%; transform:translateY(-50%); width:58px; height:58px;
            font-size:2.2rem; padding-bottom:4px;}
        .ps-lb-prev {left:2.5vw;}
        .ps-lb-next {right:2.5vw;}
        .ps-lb-off {opacity:.25; pointer-events:none;}
        .ps-lb-fb {display:flex; gap:12px; margin-top:16px; pointer-events:auto;
            z-index:6;}
        .ps-lb-fb .ps-fb-btn {min-width:130px; background:rgba(255,255,255,.95);}
        .ps-lb-open {display:flex; justify-content:center; margin-top:12px;
            pointer-events:auto; z-index:6;}
        .ps-lb-open-btn {text-decoration:none !important; color:#fff;
            background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.35);
            padding:9px 18px; border-radius:11px; font-weight:700; font-size:.9rem;
            white-space:nowrap; transition:background .15s ease, transform .12s ease;}
        .ps-lb-open-btn:hover {background:rgba(255,255,255,.28);}
        .ps-lb-open-btn:active {transform:translateY(2px);}

        /* ---- like / pass buttons (no underlines anywhere; tactile 3D press) ---- */
        .ps-react a, .ps-fb-mini a, .ps-lb-fb a {text-decoration:none !important;}

        /* card reactions: Pass + Like labelled buttons, side by side, 3D */
        .ps-react {display:flex; gap:12px; align-items:center; margin:6px 2px 14px;}
        .ps-react-btn {flex:1; padding:10px 14px; border-radius:12px; display:flex;
            align-items:center; justify-content:center; gap:6px; font-size:.88rem;
            font-weight:750; line-height:1; text-decoration:none !important;
            border:1px solid; cursor:pointer;
            transition:transform .12s ease, box-shadow .12s ease, background .12s ease;}
        .ps-react-btn:active {transform:translateY(2px);}
        .ps-react-nope {color:#dc2626; border-color:#fecaca; background:#fff;
            box-shadow:0 4px 0 #fecaca, 0 6px 12px rgba(220,38,38,.18);}
        .ps-react-nope:hover {background:#fef2f2; transform:translateY(-1px);
            box-shadow:0 5px 0 #fecaca, 0 10px 18px rgba(220,38,38,.25);}
        .ps-react-nope.on {color:#fff; background:#ef4444; border-color:#ef4444;
            box-shadow:0 4px 0 #b91c1c, 0 6px 14px rgba(239,68,68,.45);}
        .ps-react-like {color:#16a34a; border-color:#bbf7d0; background:#fff;
            box-shadow:0 4px 0 #bbf7d0, 0 6px 12px rgba(22,163,74,.18);}
        .ps-react-like:hover {background:#f0fdf4; transform:translateY(-1px);
            box-shadow:0 5px 0 #bbf7d0, 0 10px 18px rgba(22,163,74,.25);}
        .ps-react-like.on {color:#fff; background:#16a34a; border-color:#16a34a;
            box-shadow:0 4px 0 #15803d, 0 6px 14px rgba(22,163,74,.45);}

        /* table reactions: same labelled 3D pills as the cards, inline in the cell */
        .ps-fb-mini {display:flex; flex-direction:row; gap:6px; justify-content:flex-end;
            position:relative; z-index:2;}
        .ps-fb-mini-btn {display:flex; align-items:center; justify-content:center; gap:5px;
            padding:6px 10px; border-radius:10px; font-size:.75rem; font-weight:750;
            white-space:nowrap;
            line-height:1; text-decoration:none !important; border:1px solid;
            cursor:pointer; transition:transform .12s ease, box-shadow .12s ease,
            background .12s ease;}
        .ps-fb-mini-btn:active {transform:translateY(2px);}
        .ps-fb-mini-btn.ps-fb-nope {color:#dc2626; border-color:#fecaca; background:#fff;
            box-shadow:0 4px 0 #fecaca, 0 6px 12px rgba(220,38,38,.16);}
        .ps-fb-mini-btn.ps-fb-nope:hover {background:#fef2f2; transform:translateY(-1px);
            box-shadow:0 5px 0 #fecaca, 0 9px 16px rgba(220,38,38,.22);}
        .ps-fb-mini-btn.ps-fb-nope.on {color:#fff; background:#ef4444;
            border-color:#ef4444; box-shadow:0 4px 0 #b91c1c;}
        .ps-fb-mini-btn.ps-fb-like {color:#16a34a; border-color:#bbf7d0; background:#fff;
            box-shadow:0 4px 0 #bbf7d0, 0 6px 12px rgba(22,163,74,.16);}
        .ps-fb-mini-btn.ps-fb-like:hover {background:#f0fdf4; transform:translateY(-1px);
            box-shadow:0 5px 0 #bbf7d0, 0 9px 16px rgba(22,163,74,.22);}
        .ps-fb-mini-btn.ps-fb-like.on {color:#fff; background:#16a34a;
            border-color:#16a34a; box-shadow:0 4px 0 #15803d;}

        /* lightbox reaction pills: 3D, no underline */
        .ps-fb-btn {text-decoration:none !important; padding:9px 18px; border-radius:11px;
            font-weight:700; font-size:.9rem; border:1px solid; white-space:nowrap;
            transition:transform .12s ease, box-shadow .12s ease;}
        .ps-fb-btn:active {transform:translateY(2px);}
        .ps-fb-btn.ps-fb-like {color:#15803d; border-color:#16a34a;
            box-shadow:0 4px 0 #15803d;}
        .ps-fb-btn.ps-fb-like.on {color:#fff !important; background:#16a34a;}
        .ps-fb-btn.ps-fb-nope {color:#b91c1c; border-color:#ef4444;
            box-shadow:0 4px 0 #b91c1c;}
        .ps-fb-btn.ps-fb-nope.on {color:#fff !important; background:#ef4444;}

        /* whole-row stretched link (table view) */
        .ps-table tbody tr {position:relative;}
        /* row-link is absolute with the <tr> as its containing block (tr is relative),
           so it covers the WHOLE row; the photo cell must NOT be positioned or it would
           clip the link to that one cell. */
        .ps-row-link {position:absolute; inset:0; z-index:1; text-decoration:none;}
        .ps-table .ps-zoom {position:relative; z-index:2; cursor:zoom-in;}
        /* listing cell: title block left, match label right-aligned */
        .ps-tb-listing {display:flex; align-items:center; gap:12px;
            justify-content:space-between;}
        .ps-tb-lmain {min-width:0;}
        .ps-tb-listing .ps-score-pill {flex:0 0 auto;}

        /* whole-card stretched link (card view) — photo + reactions stay above it */
        .ps-card-link {position:absolute; inset:0; z-index:1; text-decoration:none;}
        .ps-card .ps-zoom {position:relative; z-index:3; cursor:zoom-in;}
        .ps-card .ps-react {position:relative; z-index:3;}

        /* price + size on one line, size right-aligned */
        .ps-price-row {display:flex; align-items:baseline; justify-content:space-between;
            gap:10px;}
        .ps-size {margin-left:auto; display:inline-block; border-radius:999px;
            padding:4px 12px; font-weight:750; font-size:.8rem; white-space:nowrap;
            background:var(--ps-brand-soft); color:var(--ps-brand);}

        /* bottom block: pinned to the card's base, away from the content */
        .ps-foot-block {margin-top:auto; padding-top:10px;}
        .ps-scoreline {margin:8px 0 2px;}
        .ps-score-pill {display:inline-block; border-radius:999px; padding:4px 12px;
            font-weight:800; font-size:.8rem;}
        .ps-foot-block .ps-react {margin:10px 2px 2px;}

        /* pass-reason chips (D29) — revealed under a passed listing */
        .ps-reasons {position:relative; z-index:3; display:flex; flex-wrap:wrap;
            align-items:center; gap:6px; margin:8px 2px 2px;}
        .ps-reasons-lbl {font-size:.72rem; font-weight:700; color:var(--ps-muted);
            text-transform:uppercase; letter-spacing:.04em; margin-right:2px;}
        .ps-reason {text-decoration:none !important; font-size:.78rem; font-weight:650;
            padding:4px 10px; border-radius:999px; border:1px solid var(--ps-line);
            background:#fff; color:var(--ps-ink); white-space:nowrap; line-height:1.4;
            transition:background .12s ease, border-color .12s ease;}
        .ps-reason:hover {border-color:#fca5a5; background:#fef2f2;}
        .ps-reason.on {background:#ef4444; border-color:#ef4444; color:#fff;}
        .ps-tb-listing .ps-reasons {margin:7px 0 1px;}

        /* contacted toggle + notes (D29) */
        .ps-contact {position:relative; z-index:3; display:flex; align-items:center;
            gap:8px; margin:8px 2px 2px;}
        .ps-contact-btn {text-decoration:none !important; font-size:.82rem; font-weight:700;
            padding:7px 12px; border-radius:10px; border:1px solid #bfdbfe;
            background:#fff; color:#2563eb; transition:background .12s ease;}
        .ps-contact-btn:hover {background:#eff6ff;}
        .ps-contact-btn.on {background:#2563eb; border-color:#2563eb; color:#fff;}
        .ps-note-ind {font-size:.9rem;}
        .ps-tb-track {margin-top:6px;}
        .ps-tb-contact {position:relative; z-index:2; text-decoration:none !important;
            font-size:.75rem; font-weight:700; padding:3px 9px; border-radius:8px;
            border:1px solid #bfdbfe; background:#fff; color:#2563eb;}
        .ps-tb-contact:hover {background:#eff6ff;}
        .ps-tb-contact.on {background:#2563eb; border-color:#2563eb; color:#fff;}
        .ps-card.contacted {border-color:#93c5fd; box-shadow:0 0 0 1px #93c5fd,
            var(--ps-shadow);}
        .ps-lb-fb + .ps-contact {justify-content:center; margin-top:12px;}
        /* contacted pill over the top-right of the photo: icon-only, expands left on hover */
        .ps-contact-fab {position:absolute; top:10px; right:10px; z-index:3;
            display:inline-flex; align-items:center; justify-content:flex-end;
            text-decoration:none !important; font-size:.76rem; font-weight:750;
            height:32px; padding:0 9px; border-radius:999px; white-space:nowrap;
            background:rgba(255,255,255,.92); color:#2563eb;
            border:1px solid rgba(255,255,255,.7);
            box-shadow:0 2px 10px -2px rgba(15,23,42,.35);
            backdrop-filter:blur(4px); transition:background .12s ease, color .12s ease;}
        .ps-contact-fab:hover {background:#fff;}
        .ps-contact-fab.on {background:#2563eb; color:#fff; border-color:#2563eb;}
        .ps-fab-ico {font-size:.95rem; line-height:1;}
        .ps-fab-note {margin-left:5px;}
        .ps-fab-lbl {max-width:0; opacity:0; overflow:hidden; margin-left:0;
            transition:max-width .18s ease, opacity .15s ease, margin-left .18s ease;}
        .ps-contact-fab:hover .ps-fab-lbl {max-width:140px; opacity:1; margin-left:6px;}

        /* card verdict accents */
        .ps-card.liked {border-color:#86efac; box-shadow:0 0 0 1px #86efac,
            var(--ps-shadow);}
        .ps-card.passed {opacity:.62;}
        .ps-card.passed:hover {opacity:1;}

        /* ---- pills (System) ---- */
        .ps-pill {border-radius:999px; padding:3px 11px; font-size:.78rem; font-weight:700;}
        .ps-ok {background:#dcfce7; color:#15803d;}
        .ps-bad {background:#fee2e2; color:#b91c1c;}
        .ps-muted-pill {background:#e2e8f0; color:#475569;}
        .ps-card-head {display:flex; justify-content:space-between; align-items:center;
            gap:12px;}

        /* ---- empty state ---- */
        .ps-empty {background:var(--ps-surface); border:1px dashed #cbd5e1;
            border-radius:20px; padding:48px 28px; text-align:center;
            box-shadow:var(--ps-shadow); margin-top:.5rem;}
        .ps-empty-ico {font-size:3rem; margin-bottom:.4rem;}
        .ps-empty-t {font-size:1.15rem; font-weight:750; color:var(--ps-ink);
            margin-bottom:.3rem;}
        .ps-empty-d {color:var(--ps-muted); font-size:.95rem; max-width:46ch;
            margin:0 auto; line-height:1.55;}
        .ps-empty-d b {color:var(--ps-brand-dk);}

        /* ---- sidebar ---- */
        section[data-testid="stSidebar"] {background:var(--ps-surface);
            border-right:1px solid var(--ps-line);}
        .ps-brand {display:flex; align-items:flex-start; gap:10px; margin:0 0 .1rem;}
        .ps-sb-rule {height:1px; background:var(--ps-line); margin:14px 2px;}
        /* never break words in the sidebar (the narrow rail would split them 1 char/line) */
        section[data-testid="stSidebar"], section[data-testid="stSidebar"] * {
            word-break:normal !important; overflow-wrap:normal !important;
            white-space:nowrap !important;}
        /* the text block must not wrap (inherited word-break would break it 1 char/line
           in the narrow rail, inflating the brand height and pushing the nav down) */
        .ps-brand > div:last-child {min-width:0; overflow:hidden;}
        .ps-brand-logo {width:38px; height:38px; min-width:38px; min-height:38px;
            flex:0 0 38px; border-radius:11px; display:flex;
            align-items:center; justify-content:center; font-size:1.2rem;
            background:linear-gradient(135deg,var(--ps-brand),#7c3aed);
            box-shadow:0 6px 14px -4px rgba(79,70,229,.6);}
        .ps-brand-name {font-size:1.2rem; font-weight:850; letter-spacing:-.02em;
            line-height:1; background:var(--ps-grad); -webkit-background-clip:text;
            background-clip:text; color:transparent; width:fit-content;
            white-space:nowrap; word-break:normal; overflow-wrap:normal;}
        .ps-brand-sub {color:var(--ps-muted); font-size:.74rem; font-weight:600;
            margin:1px 0 0; white-space:nowrap; word-break:normal; overflow-wrap:normal;}

        /* ---- collapsible icon rail: narrow by default, expands on hover ---- */
        section[data-testid="stSidebar"] {
            width:78px !important; min-width:78px !important; max-width:78px !important;
            transform:none !important;  /* keep on-screen even if auto-collapsed */
            transition:width .18s ease, min-width .18s ease, max-width .18s ease;
            overflow:visible !important; z-index:1000;}
        /* drag-to-resize handle is redundant — width is hover-driven */
        section[data-testid="stSidebar"] [style*="col-resize"] {display:none !important;}
        /* tighten inner padding so 78px isn't eaten by gutters; pin content to top */
        section[data-testid="stSidebar"] > div {padding-left:.55rem !important;
            padding-right:.55rem !important; padding-top:1rem !important;}
        /* keep nav pinned to the top in BOTH states (Streamlit vertically centers the
           short content when collapsed) */
        section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            justify-content:flex-start !important; align-content:flex-start !important;}
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            display:none !important;}
        .ps-brand {margin-top:0 !important;}
        section[data-testid="stSidebar"]:hover {
            width:268px !important; min-width:268px !important; max-width:268px !important;
            box-shadow:6px 0 28px -10px rgba(15,23,42,.18);}
        section[data-testid="stSidebar"]:hover > div {padding-left:1.1rem !important;
            padding-right:1.1rem !important;}
        /* custom nav */
        .ps-nav {display:flex; flex-direction:column; gap:3px;}
        .ps-nav-item {display:flex; align-items:center; gap:12px;
            padding:9px 10px; border-radius:11px; text-decoration:none !important;
            color:var(--ps-ink); font-weight:650; font-size:.95rem;
            transition:background .12s ease;}
        .ps-nav-item:hover {background:var(--ps-brand-soft);}
        .ps-nav-item.active {background:linear-gradient(135deg,#eef2ff,#f3f0ff);
            color:var(--ps-brand-dk); box-shadow:inset 3px 0 0 0 var(--ps-brand);}
        .ps-nav-ico {flex:0 0 auto; width:24px; text-align:center; font-size:1.15rem;}
        .ps-nav-lbl {white-space:nowrap;}
        /* hide everything text-heavy while the rail is narrow */
        section[data-testid="stSidebar"] :is(.ps-nav-lbl,.ps-brand-name,.ps-brand-sub,
            .ps-section) {opacity:0; transition:opacity .12s ease; pointer-events:none;}
        section[data-testid="stSidebar"] hr {display:none;}
        section[data-testid="stSidebar"]:hover :is(.ps-nav-lbl,.ps-brand-name,
            .ps-brand-sub,.ps-section) {opacity:1; pointer-events:auto;}

        /* Refresh box (button + "last synced") pinned to the bottom of the rail — visible
           collapsed & expanded. Icon-only when narrow, full label + caption on hover. */
        section[data-testid="stSidebar"] {position:relative;}
        section[data-testid="stSidebar"] .st-key-refreshbox {
            position:absolute !important; left:0; right:0; bottom:14px;
            margin:0 !important; padding:0 .6rem !important; box-sizing:border-box;}
        section[data-testid="stSidebar"]:hover .st-key-refreshbox {
            padding:0 1.1rem !important;}
        section[data-testid="stSidebar"]:not(:hover) .st-key-refresh_now button {
            display:flex !important; align-items:center; justify-content:center;
            width:46px !important; height:46px !important; min-width:46px !important;
            margin:0 auto !important; padding:0 !important; border-radius:13px;
            background:transparent !important; border:none !important;
            box-shadow:none !important;}
        section[data-testid="stSidebar"]:not(:hover) .st-key-refresh_now button * {
            font-size:0 !important; margin:0 !important; padding:0 !important;}
        section[data-testid="stSidebar"]:not(:hover) .st-key-refresh_now button::before {
            content:"🔄"; font-size:1.35rem !important; line-height:1;}
        /* syncing → hourglass icon when collapsed */
        section[data-testid="stSidebar"]:not(:hover) .st-key-refresh_now
            button:disabled::before {content:"⏳";}
        /* "last synced" caption: hidden when collapsed, centered + muted when expanded */
        .ps-sync {font-size:.74rem; font-weight:600; color:var(--ps-muted);
            text-align:center; margin:0 0 6px; opacity:0; transition:opacity .12s ease;}
        section[data-testid="stSidebar"]:hover .ps-sync {opacity:1;}

        /* ---- post-scrape result banner ---- */
        .ps-scrape-banner {border-radius:14px; padding:14px 18px; margin:0 0 1.2rem;
            border:1px solid var(--ps-line); animation:ps-fade .3s ease;}
        .ps-scrape-banner.ok {background:linear-gradient(135deg,#ecfdf5,#f0fdf4);
            border-color:#a7f3d0;}
        .ps-scrape-banner.neutral {background:var(--ps-surface);}
        .ps-scrape-head {font-size:1.05rem; font-weight:800; color:var(--ps-ink);
            letter-spacing:-.01em;}
        .ps-scrape-banner.ok .ps-scrape-head {color:#047857;}
        .ps-scrape-sub {font-size:.85rem; color:var(--ps-muted); margin-top:2px;
            font-weight:600;}
        @keyframes ps-fade {from{opacity:0; transform:translateY(-4px);} to{opacity:1;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(title: str, subtitle: str) -> None:
    st.markdown(f"<div class='ps-h1'>{html.escape(title)}</div>"
                f"<div class='ps-sub'>{html.escape(subtitle)}</div>",
                unsafe_allow_html=True)


def _score_class(pct: int) -> str:
    return "ps-hi" if pct >= 80 else "ps-mid" if pct >= 60 else "ps-lo"


def _empty_state(icon: str, title: str, desc_html: str) -> None:
    """Friendly, on-brand empty/zero-result panel (desc_html is trusted markup)."""
    st.markdown(
        f"<div class='ps-empty'><div class='ps-empty-ico'>{icon}</div>"
        f"<div class='ps-empty-t'>{html.escape(title)}</div>"
        f"<div class='ps-empty-d'>{desc_html}</div></div>",
        unsafe_allow_html=True)


# Pass reasons (D29): captured when a listing is passed, to learn why over time.
PASS_REASONS = [
    ("over_budget", "💸 Over budget"),
    ("fake", "🎭 Fake / spam"),
    ("location", "📍 Location"),
    ("condition", "🏚️ Size / condition"),
    ("disliked", "👎 Didn't like"),
]
_REASON_LABEL = dict(PASS_REASONS)


def _reason_chips(lid: int, active: str | None, state: dict) -> str:
    """Pass-reason chips shown under a passed listing — click to tag *why* it was passed
    (D29). Each is a query-param link; re-clicking the active reason clears it."""
    chips = []
    for code, label in PASS_REASONS:
        on = " on" if active == code else ""
        href = "?" + _build_qs(state, fb="nope", reason=code, id=int(lid))
        chips.append(f"<a class='ps-reason{on}' target='_self' href='{href}'>{label}</a>")
    return ("<div class='ps-reasons'><span class='ps-reasons-lbl'>Why pass?</span>"
            + "".join(chips) + "</div>")


def _contact_ctrl(lid: int, track: dict | None, state: dict) -> str:
    """A 'mark contacted' toggle + a 📝 indicator when notes exist (D29). Query-param link;
    contacted state is stamped with the time. Notes are edited on the Shortlist page."""
    contacted = bool(track and track.get("contacted_at"))
    has_note = bool(track and track.get("notes"))
    on = " on" if contacted else ""
    href = "?" + _build_qs(state, contact=1, id=int(lid))
    label = "✅ Contacted" if contacted else "📞 Mark contacted"
    note = " <span class='ps-note-ind' title='Has notes'>📝</span>" if has_note else ""
    return (f"<div class='ps-contact'>"
            f"<a class='ps-contact-btn{on}' target='_self' href='{href}'>{label}</a>{note}"
            "</div>")


def _fb_row(m: dict, verdict: str | None, state: dict, reason: str | None = None) -> str:
    """Like / Not-interested buttons for a listing. Each is a link that reloads with a
    query param (Streamlit has no in-HTML callbacks); the top-level handler records it.
    Clicking the active verdict again clears it (toggle). `state` carries the full page
    state (view/filters) so the click preserves everything. When passed, a reason-chip
    row is revealed beneath (D29)."""
    lid = m.get("id")
    if not lid:
        return ""
    like_on = " on" if verdict == "like" else ""
    nope_on = " on" if verdict == "nope" else ""
    nope_h = "?" + _build_qs(state, fb="nope", id=int(lid))
    like_h = "?" + _build_qs(state, fb="like", id=int(lid))
    chips = _reason_chips(int(lid), reason, state) if verdict == "nope" else ""
    return (
        "<div class='ps-react'>"
        f"<a class='ps-react-btn ps-react-nope{nope_on}' target='_self' "
        f"href='{nope_h}'>👎 Pass</a>"
        f"<a class='ps-react-btn ps-react-like{like_on}' target='_self' "
        f"href='{like_h}'>👍 Like</a>"
        "</div>" + chips)


def _maps_url(sector) -> str:
    """Google Maps search link for a Noida sector (click to see where it is)."""
    s = str(sector).strip()
    q = s if "sector" in s.lower() else f"Sector {s}"
    if "noida" not in q.lower():
        q += " Noida"
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


def _match_card_html(m: dict, lb_id: int | None = None,
                     verdict: str | None = None, state: dict | None = None,
                     reason: str | None = None, track: dict | None = None) -> str:
    """Build one property card. All user/listing strings are HTML-escaped.
    lb_id, when set, makes the photo open the lightbox gallery at that index."""
    state = state or {"pg": "Matches"}
    pct = round((m.get("score") or 0) * 100)
    has_score = m.get("score") is not None
    sc = _score_class(pct)
    price = m.get("price")
    price_html = (f"₹ {rupees_to_cr(price):g}<small> Cr</small>"
                  if price else "<small>Price on request</small>")
    title = html.escape(m.get("title") or "Untitled listing")
    sector = m.get("sector")
    url = m.get("url") or ""

    img = m.get("image_url")
    if img:
        photo = f"<img src='{html.escape(img, quote=True)}' loading='lazy' alt=''>"
        if lb_id is not None:
            photo = f"<a class='ps-zoom' href='#lb{lb_id}'>{photo}</a>"
    else:
        photo = "<div class='ps-photo-ph'>🏠</div>"
    # Sector tag doubles as a Google Maps link (sits above the stretched card link).
    sectortag = (
        f"<a class='ps-sectortag' href='{_maps_url(sector)}' target='_blank' "
        f"rel='noopener' title='Find Sector {html.escape(str(sector))} on Google Maps'>"
        f"📍 {html.escape(str(sector))} <span class='ps-map-ic'>🗺️</span></a>"
        if sector else "")

    # Size now rides inline with the price (right-aligned), not as a chip.
    size_html = (f"<span class='ps-size'>{m['size_sqm']:.0f} sqm</span>"
                 if m.get("size_sqm") else "")

    chips = []
    if m.get("advertiser"):
        chips.append(f"<span class='ps-chip ps-chip-n'>{html.escape(m['advertiser'])}</span>")
    auth = m.get("approving_authority")
    if auth:
        chips.append(f"<span class='ps-chip ps-chip-n'>{html.escape(str(auth))}</span>")
    chips_html = "".join(chips) or "<span class='ps-chip ps-chip-n'>details on listing</span>"

    desc = m.get("description")
    desc_html = f"<div class='ps-desc'>{html.escape(desc)}</div>" if desc else ""

    foot_bits = []
    if m.get("requirement_id"):
        foot_bits.append(f"Req #{m['requirement_id']}")
    if m.get("owner"):
        foot_bits.append(html.escape(m["owner"]))
    foot_meta = " · ".join(foot_bits) or "&nbsp;"
    # Whole card opens the listing in a new tab (stretched link); the photo (lightbox)
    # and the Like/Pass buttons sit above it via z-index so they still work.
    card_link = (f"<a class='ps-card-link' href='{html.escape(url, quote=True)}' "
                 "target='_blank' rel='noopener'></a>") if url else ""
    badge = (f"<span class='ps-score-pill {sc}'>{pct}% match</span>"
             if has_score else "")
    fb = _fb_row(m, verdict, state, reason)
    contacted = bool(track and track.get("contacted_at"))
    # Contacted toggle floats as a pill over the top-right of the photo.
    contact_fab = ""
    if m.get("id"):
        c_on = " on" if contacted else ""
        c_href = "?" + _build_qs(state, contact=1, id=int(m["id"]))
        c_ico = "✅" if contacted else "📞"
        c_lbl = "Contacted" if contacted else "Mark contacted"
        c_note = ("<span class='ps-fab-note'>📝</span>"
                  if (track and track.get("notes")) else "")
        # Icon-only by default; expands leftward on hover to reveal the label.
        contact_fab = (f"<a class='ps-contact-fab{c_on}' target='_self' href='{c_href}' "
                       f"title='Mark as contacted'><span class='ps-fab-ico'>{c_ico}</span>"
                       f"<span class='ps-fab-lbl'>{c_lbl}</span>{c_note}</a>")

    return (
        f"<div class='ps-card{(' liked' if verdict == 'like' else '')}"
        f"{(' passed' if verdict == 'nope' else '')}"
        f"{(' contacted' if contacted else '')}'>"
        f"{card_link}"
        f"<div class='ps-photo'>{photo}{sectortag}{contact_fab}"
        f"{'<span class=\"ps-new-tag\">🆕 New</span>' if m.get('__new__') else ''}</div>"
        "<div class='ps-body'>"
        f"<div class='ps-price-row'><span class='ps-price'>{price_html}</span>"
        f"{size_html}</div>"
        f"<div class='ps-title'>{title}</div>"
        f"{desc_html}"
        f"<div class='ps-chips'>{chips_html}</div>"
        "<div class='ps-foot-block'>"
        f"<div class='ps-card-foot'><span class='ps-meta'>{foot_meta}</span>{badge}</div>"
        f"{fb}"
        "</div></div></div>")


_SCORE_FILL = {"ps-hi": "#16a34a", "ps-mid": "#d97706", "ps-lo": "#94a3b8"}


def _match_row_html(m: dict, lb_id: int | None = None,
                    verdict: str | None = None, state: dict | None = None,
                    reason: str | None = None, track: dict | None = None) -> str:
    """One styled table row for the Matches table view. All strings HTML-escaped."""
    state = state or {"pg": "Matches"}
    pct = round((m.get("score") or 0) * 100)
    has_score = m.get("score") is not None
    sc = _score_class(pct)

    img = m.get("image_url")
    if img:
        photo = (f"<img class='ps-tb-photo' src='{html.escape(img, quote=True)}' "
                 "loading='lazy' alt=''>")
        if lb_id is not None:
            photo = f"<a class='ps-zoom' href='#lb{lb_id}'>{photo}</a>"
    else:
        photo = "<div class='ps-tb-photo ps-tb-photo-ph'>🏠</div>"

    title = html.escape(m.get("title") or "Untitled listing")
    sub_bits = []
    if m.get("sector"):
        sub_bits.append(
            f"<a class='ps-tb-map' href='{_maps_url(m['sector'])}' target='_blank' "
            f"rel='noopener' title='Find on Google Maps'>📍 "
            f"{html.escape(str(m['sector']))} 🗺️</a>")
    if m.get("advertiser"):
        sub_bits.append(html.escape(m["advertiser"]))
    auth = m.get("approving_authority")
    if auth:
        sub_bits.append(html.escape(str(auth)))
    sub = " · ".join(sub_bits)
    sub_html = f"<div class='ps-tb-sub'>{sub}</div>" if sub else ""

    price = m.get("price")
    price_html = (f"₹ {rupees_to_cr(price):g}<small> Cr</small>"
                  if price else "<small>On request</small>")
    size_html = f"{m['size_sqm']:.0f} <small>sqm</small>" if m.get("size_sqm") else "—"

    url = m.get("url") or ""
    # Stretched link: covers the whole row so clicking anywhere opens the listing. The
    # photo (lightbox) and the Like/Pass buttons sit above it (z-index) so they still work.
    row_link = (f"<a class='ps-row-link' href='{html.escape(url, quote=True)}' "
                "target='_blank' rel='noopener'></a>") if url else ""

    lid = m.get("id")
    if lid:
        like_on = " on" if verdict == "like" else ""
        nope_on = " on" if verdict == "nope" else ""
        like_h = "?" + _build_qs(state, fb="like", id=int(lid))
        nope_h = "?" + _build_qs(state, fb="nope", id=int(lid))
        fb = (f"<div class='ps-fb-mini'>"
              f"<a class='ps-fb-mini-btn ps-fb-like{like_on}' target='_self' "
              f"href='{like_h}'>👍 Like</a>"
              f"<a class='ps-fb-mini-btn ps-fb-nope{nope_on}' target='_self' "
              f"href='{nope_h}'>👎 Pass</a>"
              "</div>")
    else:
        fb = ""

    score_lbl = (f"<span class='ps-score-pill {sc}'>{pct}%</span>" if has_score else "")
    # When passed, reason chips wrap under the title (the Listing column has the room).
    chips = _reason_chips(int(lid), reason, state) if (lid and verdict == "nope") else ""
    # Compact contacted toggle (+ note indicator) under the title.
    tb_track = ""
    if lid:
        contacted = bool(track and track.get("contacted_at"))
        c_on = " on" if contacted else ""
        c_href = "?" + _build_qs(state, contact=1, id=int(lid))
        c_lbl = "✅ Contacted" if contacted else "📞 Contact"
        c_note = " 📝" if (track and track.get("notes")) else ""
        tb_track = (f"<div class='ps-tb-track'><a class='ps-tb-contact{c_on}' "
                    f"target='_self' href='{c_href}'>{c_lbl}{c_note}</a></div>")
    return (
        "<tr>"
        f"<td class='ps-tb-photocell'>{row_link}{photo}</td>"
        f"<td><div class='ps-tb-listing'><div class='ps-tb-lmain'>"
        f"<div class='ps-tb-title'>{title}"
        f"{' <span class=\"ps-new-pill\">NEW</span>' if m.get('__new__') else ''}</div>"
        f"{sub_html}{chips}{tb_track}"
        f"</div>{score_lbl}</div></td>"
        f"<td class='ps-tb-size'>{size_html}</td>"
        f"<td class='ps-tb-price'>{price_html}</td>"
        f"<td class='ps-tb-act'>{fb}</td>"
        "</tr>")


def _sort_th(label: str, field: str, state: dict, sort_code: str) -> str:
    """A clickable, sortable table header. Clicking toggles asc↔desc for that column via
    the shared ?sort= state; shows ▲/▼ when active, ↕ otherwise."""
    asc, desc = f"{field}_asc", f"{field}_desc"
    nxt = desc if sort_code == asc else asc
    arrow = "▲" if sort_code == asc else "▼" if sort_code == desc else "↕"
    active = " active" if sort_code in (asc, desc) else ""
    href = "?" + _build_qs(state, sort=nxt)
    return (f"<th><a class='ps-th-sort{active}' target='_self' href='{href}'>{label}"
            f"<span class='ps-th-arr'>{arrow}</span></a></th>")


def _match_table_html(rows: list[dict], lb_of=lambda m: None, fb_of=lambda m: None,
                      state: dict | None = None, sort_code: str = "best",
                      reason_of=lambda m: None, track_of=lambda m: None) -> str:
    """Full styled table for the Matches table view (replaces st.dataframe)."""
    state = state or {"pg": "Matches"}
    body = "".join(_match_row_html(m, lb_of(m), fb_of(m), state, reason_of(m),
                                   track_of(m)) for m in rows)
    return (
        "<div class='ps-table-wrap'><table class='ps-table'>"
        "<colgroup><col style='width:76px'><col><col style='width:13%'>"
        "<col style='width:15%'><col style='width:16%'></colgroup>"
        "<thead><tr><th></th><th>Listing</th>"
        f"{_sort_th('Size', 'size', state, sort_code)}"
        f"{_sort_th('Price', 'price', state, sort_code)}"
        "<th></th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>")


def _lightbox_html(imaged: list[dict], fb_of=lambda m: None,
                   state: dict | None = None, reason_of=lambda m: None,
                   track_of=lambda m: None) -> str:
    """Pure-CSS lightbox gallery (uses :target, no JS — Streamlit strips <script>).
    `imaged` is the ordered list of matches that have an image; each opens at #lb<k>
    and links prev/next to walk across all properties. All strings HTML-escaped."""
    state = state or {"pg": "Matches"}
    n = len(imaged)
    if not n:
        return ""
    out = ["<div class='ps-lb-root'>"]
    for k, m in enumerate(imaged):
        img = html.escape(m.get("image_url") or "", quote=True)
        title = html.escape(m.get("title") or "Untitled listing")
        price = (f"₹ {rupees_to_cr(m['price']):g} Cr" if m.get("price") else "")
        sect = html.escape(str(m["sector"])) if m.get("sector") else ""
        cap = " · ".join(x for x in (title, sect, price) if x)
        if m.get("__new__"):
            cap = "<span class='ps-new-pill'>NEW</span> " + cap
        prev = (f"<a class='ps-lb-nav ps-lb-prev' href='#lb{k-1}'>‹</a>" if k > 0
                else "<span class='ps-lb-nav ps-lb-prev ps-lb-off'>‹</span>")
        nxt = (f"<a class='ps-lb-nav ps-lb-next' href='#lb{k+1}'>›</a>" if k < n - 1
               else "<span class='ps-lb-nav ps-lb-next ps-lb-off'>›</span>")
        verdict, lid = fb_of(m), m.get("id")
        controls = ""
        if lid:
            like_on = " on" if verdict == "like" else ""
            nope_on = " on" if verdict == "nope" else ""
            like_h = "?" + _build_qs(state, fb="like", id=int(lid))
            nope_h = "?" + _build_qs(state, fb="nope", id=int(lid))
            controls = (
                "<div class='ps-lb-fb'>"
                f"<a class='ps-fb-btn ps-fb-like{like_on}' target='_self' "
                f"href='{like_h}'>👍 Like</a>"
                f"<a class='ps-fb-btn ps-fb-nope{nope_on}' target='_self' "
                f"href='{nope_h}'>👎 Pass</a>"
                "</div>")
            if verdict == "nope":
                controls += _reason_chips(int(lid), reason_of(m), state)
            controls += _contact_ctrl(int(lid), track_of(m), state)
        url = m.get("url")
        open_links = ""
        if m.get("sector"):
            open_links += (f"<a class='ps-lb-open-btn ps-lb-map' "
                           f"href='{_maps_url(m['sector'])}' target='_blank' "
                           "rel='noopener'>📍 Sector on map</a>")
        if url:
            href = html.escape(url, quote=True)
            open_links += (f"<a class='ps-lb-open-btn' href='{href}' "
                           "target='_blank' rel='noopener'>Open listing ↗</a>")
        if open_links:
            controls += f"<div class='ps-lb-open'>{open_links}</div>"
        desc = m.get("description")
        desc_html = f"<div class='ps-lb-desc'>{html.escape(desc)}</div>" if desc else ""
        out.append(
            f"<div class='ps-lb' id='lb{k}'>"
            "<a class='ps-lb-backdrop' href='#_'></a>"
            "<a class='ps-lb-close' href='#_'>✕</a>"
            f"{prev}{nxt}"
            "<div class='ps-lb-stage'>"
            f"<img class='ps-lb-img' src='{img}' loading='lazy' alt=''>"
            f"<div class='ps-lb-cap'>{cap}<span class='ps-lb-count'>"
            f"{k+1} / {n}</span></div>{desc_html}{controls}"
            "</div></div>")
    out.append("</div>")
    return "".join(out)


# Initialise schema once per process (idempotent — safe on every rerun).
db.init()
st.set_page_config(page_title="prop-search", page_icon="🏡", layout="wide",
                   initial_sidebar_state="expanded")
_inject_css()

# Like/Pass clicks arrive as query params (?fb=like&id=..&pg=..) because HTML rendered via
# st.markdown can't call Python directly. Record, then strip the params (keeping the page)
# so a refresh doesn't re-fire. set_feedback toggles off if the same verdict is re-clicked.
_qp = st.query_params
if "fb" in _qp and "id" in _qp:
    try:
        db.set_feedback(int(_qp["id"]), _qp.get("fb"), _qp.get("reason"))
    except Exception:  # noqa: BLE001 - a bad/stale id must never crash the page
        pass
    for _k in ("fb", "id", "reason"):
        if _k in st.query_params:
            del st.query_params[_k]
    st.rerun()
# Contacted toggle (?contact=1&id=..) — same in-HTML-link pattern (D29).
if "contact" in _qp and "id" in _qp:
    try:
        db.set_contacted(int(_qp["id"]))  # toggle
    except Exception:  # noqa: BLE001
        pass
    for _k in ("contact", "id"):
        if _k in st.query_params:
            del st.query_params[_k]
    st.rerun()

# ------------------------------------------------------------------------------- sidebar
st.sidebar.markdown(
    "<div class='ps-brand'>"
    "<div class='ps-brand-logo'>🏡</div>"
    "<div><div class='ps-brand-name'>prop-search</div>"
    "<div class='ps-brand-sub'>Noida kothi finder</div></div></div>",
    unsafe_allow_html=True)
st.sidebar.markdown("<div class='ps-sb-rule'></div>", unsafe_allow_html=True)
_NAV = ["Matches", "Shortlist", "Requirements", "System", "Settings"]
_ICONS = {"Matches": "🎯", "Shortlist": "💚", "Requirements": "📋",
          "System": "🩺", "Settings": "⚙️"}
_pg = st.query_params.get("pg")
PAGE = _pg if _pg in _NAV else "Matches"
# Keep ?pg= in sync so Like/Pass links carry the user back to the page they're on.
if st.query_params.get("pg") != PAGE:
    st.query_params["pg"] = PAGE
# Custom HTML nav (anchors that set ?pg=). Replaces st.radio so the sidebar can be a
# hover-expand icon rail — emoji always visible, label revealed on hover (see CSS).
_nav_html = "<nav class='ps-nav'>"
for _p in _NAV:
    _cls = "ps-nav-item active" if _p == PAGE else "ps-nav-item"
    _nav_html += (f"<a class='{_cls}' href='?pg={_p}' target='_self'>"
                  f"<span class='ps-nav-ico'>{_ICONS[_p]}</span>"
                  f"<span class='ps-nav-lbl'>{_p}</span></a>")
_nav_html += "</nav>"
st.sidebar.markdown(_nav_html, unsafe_allow_html=True)

def _last_synced_caption():
    runs = db.recent_runs(1)
    fin = runs[0].get("finished_at") if runs else None
    rel = _relative_time(fin)
    txt = f"Last synced {rel}" if rel else "Not synced yet"
    st.markdown(f"<div class='ps-sync'>{txt}</div>", unsafe_allow_html=True)


@st.fragment(run_every=2)
def _refresh_running():
    """Polls the background scrape every 2s WITHOUT blocking the rest of the app."""
    proc = st.session_state.get("scrape_proc")
    with st.container(key="refreshbox"):
        if proc is not None and proc.poll() is None:
            _last_synced_caption()
            st.button("⏳ Syncing…", type="primary", use_container_width=True,
                      key="refresh_now", disabled=True)
        else:
            if proc is not None:  # just finished -> capture result, then full rerun
                ok, msg = finish_scrape_bg(proc)
                st.session_state["scrape_result"] = {"ok": ok, "msg": msg}
                st.session_state.pop("scrape_proc", None)
            st.rerun()  # full rerun: back to idle + show the result banner


def _refresh_idle():
    with st.container(key="refreshbox"):
        _last_synced_caption()
        if st.button("🔄 Refresh listings now", type="primary",
                     use_container_width=True, key="refresh_now"):
            start_scrape_bg()
            st.rerun()


with st.sidebar:
    if st.session_state.get("scrape_proc") is not None:
        _refresh_running()
    else:
        _refresh_idle()

# Show the outcome of the last on-demand scrape (survives the post-run rerun).
_res = st.session_state.pop("scrape_result", None)
if _res:
    if not _res["ok"]:
        st.error(_res["msg"])
    else:
        _s = _res["msg"] if isinstance(_res["msg"], dict) else {}
        _new = _s.get("new_matches", 0)
        _parsed = _s.get("parsed_ok", 0)
        _portals = _s.get("portals_run", 0)
        _errors = _s.get("parse_errors", 0)
        _notified = _s.get("notified", 0)
        if _new:
            _head = f"🎉 {_new} new match{'es' if _new != 1 else ''} found"
            _tone = "ok"
        else:
            _head = "✓ Scrape complete — no new matches this time"
            _tone = "neutral"
        _bits = [f"{_parsed} listings scanned",
                 f"{_portals} portal{'s' if _portals != 1 else ''}"]
        if _notified:
            _bits.append(f"{_notified} Telegram alert{'s' if _notified != 1 else ''} sent")
        if _errors:
            _bits.append(f"⚠️ {_errors} parse error{'s' if _errors != 1 else ''}")
        st.markdown(
            f"<div class='ps-scrape-banner {_tone}'>"
            f"<div class='ps-scrape-head'>{_head}</div>"
            f"<div class='ps-scrape-sub'>{' · '.join(_bits)}</div></div>",
            unsafe_allow_html=True)



# ============================================================ PAGE — Requirements (D9)
def _parse_sizes(text: str) -> list[int]:
    """Parse a comma-separated sizes string into a list of ints (ignores junk)."""
    out = []
    for tok in text.split(","):
        tok = tok.strip()
        if tok:
            try:
                out.append(int(float(tok)))
            except ValueError:
                pass
    return out


def _requirement_fields(prefix: str, r: dict | None = None) -> dict:
    """Shared requirement input fields (used by the New and Edit dialogs). Returns the
    collected, parsed values. `prefix` keeps widget keys unique between dialogs."""
    _pt_labels = dict(pt.choices())
    _pt_keys = list(_pt_labels)
    c1, c2 = st.columns(2)
    owner = c1.text_input("Owner (name / email)", value=(r["owner"] if r else ""),
                          key=f"{prefix}_owner", placeholder="e.g. nitin")
    pt_idx = _pt_keys.index(pt.category_of(r["property_type"])) if r else 0
    ptype = c2.selectbox("Property type", _pt_keys, index=pt_idx,
                         format_func=lambda k: _pt_labels[k], key=f"{prefix}_pt")
    c3, c4 = st.columns(2)
    bmin = c3.number_input("Budget min (Cr)", min_value=0.0, step=0.1,
                           value=(rupees_to_cr(r["budget_min"]) if r else 4.0),
                           key=f"{prefix}_bmin")
    bmax = c4.number_input("Budget max (Cr)", min_value=0.0, step=0.1,
                           value=(rupees_to_cr(r["budget_max"]) if r else 5.0),
                           key=f"{prefix}_bmax")
    c5, c6 = st.columns(2)
    sizes_txt = c5.text_input(
        "Sizes (sqm, comma-separated)", key=f"{prefix}_sz",
        value=(", ".join(str(s) for s in r["sizes_sqm"]) if r
               else ", ".join(str(s) for s in SIZE_OPTIONS)))
    tol = c6.number_input("Size tolerance (%)", min_value=0.0, step=1.0,
                          value=(float(r["size_tolerance_pct"]) if r else 30.0),
                          key=f"{prefix}_tol")
    sectors_txt = st.text_input(
        "Sectors (comma-separated; empty = all Noida)", key=f"{prefix}_sc",
        value=(", ".join(r["sectors"]) if r else ""),
        placeholder="e.g. 28, 50, 105")
    return {"owner": owner.strip(), "ptype": ptype, "bmin": bmin, "bmax": bmax,
            "sizes": _parse_sizes(sizes_txt), "tol": tol,
            "sectors": [s.strip() for s in sectors_txt.split(",") if s.strip()]}


@st.dialog("New requirement")
def _new_requirement_dialog():
    v = _requirement_fields("new")
    st.write("")
    if st.button("Create requirement", type="primary", use_container_width=True):
        if not v["owner"]:
            st.error("Owner is required.")
        else:
            db.add_requirement(
                owner=v["owner"], budget_min=cr_to_rupees(v["bmin"]),
                budget_max=cr_to_rupees(v["bmax"]), sizes_sqm=v["sizes"],
                sectors=v["sectors"], property_type=v["ptype"],
                size_tolerance_pct=v["tol"])
            st.rerun()


@st.dialog("Edit requirement")
def _edit_requirement_dialog(r: dict):
    v = _requirement_fields(f"edit{r['id']}", r)
    active = st.toggle("Active — included in every scrape", value=bool(r["active"]),
                       key=f"edit{r['id']}_active")
    st.divider()
    if st.button("💾 Save changes", type="primary", use_container_width=True,
                 key=f"save{r['id']}"):
        if not v["owner"]:
            st.error("Owner is required.")
        else:
            db.update_requirement(
                r["id"], owner=v["owner"], property_type=v["ptype"],
                sizes_sqm=v["sizes"], size_tolerance_pct=v["tol"],
                budget_min=cr_to_rupees(v["bmin"]), budget_max=cr_to_rupees(v["bmax"]),
                sectors=v["sectors"], active=1 if active else 0)
            st.rerun()

    # Delete: a plain button that reveals an inline confirm (no confusing checkbox).
    # The dialog is a fragment — use scope="fragment" so toggling confirm/cancel re-renders
    # WITHIN the open modal; only the actual delete does a full rerun to close + refresh.
    del_key = f"confirm_del{r['id']}"
    if st.session_state.get(del_key):
        st.caption("⚠️ Delete this requirement permanently? This can't be undone.")
        d1, d2 = st.columns(2)
        if d1.button("Yes, delete", type="primary", use_container_width=True,
                     key=f"yesdel{r['id']}"):
            db.delete_requirement(r["id"])
            st.session_state.pop(del_key, None)
            st.rerun()
        if d2.button("Cancel", use_container_width=True, key=f"canceldel{r['id']}"):
            st.session_state.pop(del_key, None)
            st.rerun(scope="fragment")
    elif st.button("🗑 Delete requirement", use_container_width=True,
                   key=f"del{r['id']}"):
        st.session_state[del_key] = True
        st.rerun(scope="fragment")


def page_requirements():
    _header("Requirements", "Your saved property queries. The scheduler checks every "
                            "active one each run.")
    reqs = db.list_requirements()

    if not reqs:
        st.write("")
        if st.button("➕  New requirement", type="primary"):
            _new_requirement_dialog()
        _empty_state(
            "📝", "No requirements yet",
            "Click <b>➕ New requirement</b> to tell prop-search your budget, sectors and "
            "size. The scheduler then hunts for matches every 6 hours.")
        return

    # ---- search + filters + new ----
    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 1.6], vertical_alignment="bottom")
    query = fc1.text_input("Search", placeholder="🔍 Owner or sector…",
                           label_visibility="collapsed", key="req_q").strip().lower()
    _types = ["All types"] + [lbl for _, lbl in pt.choices()]
    type_f = fc2.selectbox("Type", _types, label_visibility="collapsed", key="req_typef")
    status_f = fc3.selectbox("Status", ["All", "Active", "Paused"],
                             label_visibility="collapsed", key="req_statusf")
    with fc4:
        if st.button("➕  New", type="primary", use_container_width=True):
            _new_requirement_dialog()

    filtered = []
    for r in reqs:
        if status_f == "Active" and not r["active"]:
            continue
        if status_f == "Paused" and r["active"]:
            continue
        if type_f != "All types" and pt.label_of(r["property_type"]) != type_f:
            continue
        if query:
            hay = (r["owner"] + " " + " ".join(str(s) for s in r["sectors"])).lower()
            if query not in hay:
                continue
        filtered.append(r)

    st.markdown(f"<div class='ps-section' style='margin:.6rem 0 .5rem;'>"
                f"{len(filtered)} of {len(reqs)} shown</div>", unsafe_allow_html=True)

    if not filtered:
        _empty_state("🔍", "No requirements match",
                     "Try a different search term or clear the filters.")
        return

    cols_w = [2.4, 1.5, 1.3, 2.3, 1.1, 0.9]
    with st.container(key="reqtable"):
        h = st.columns(cols_w, vertical_alignment="center")
        for col, lbl in zip(h, ["Owner", "Type", "Budget", "Sectors", "Status", ""]):
            col.markdown(f"<div class='ps-th'>{lbl}</div>", unsafe_allow_html=True)
        for r in filtered:
            row = st.columns(cols_w, vertical_alignment="center")
            row[0].markdown(f"<div class='ps-td ps-td-strong'>{html.escape(r['owner'])}"
                            "</div>", unsafe_allow_html=True)
            row[1].markdown(f"<div class='ps-td'>{html.escape(pt.label_of(r['property_type']))}"
                            "</div>", unsafe_allow_html=True)
            budget = (f"₹ {rupees_to_cr(r['budget_min']):g}–"
                      f"{rupees_to_cr(r['budget_max']):g} Cr")
            row[2].markdown(f"<div class='ps-td'>{budget}</div>", unsafe_allow_html=True)
            sectors = ", ".join(r["sectors"]) if r["sectors"] else "all Noida"
            row[3].markdown(f"<div class='ps-td'>📍 {html.escape(sectors)}</div>",
                            unsafe_allow_html=True)
            stat = ("<span class='ps-stat ps-stat-on'>● Active</span>" if r["active"]
                    else "<span class='ps-stat ps-stat-off'>● Paused</span>")
            row[4].markdown(f"<div class='ps-td'>{stat}</div>", unsafe_allow_html=True)
            with row[5]:
                if st.button("✏️", key=f"editbtn{r['id']}", use_container_width=True,
                             help="Edit requirement"):
                    _edit_requirement_dialog(r)


# ============================================================== PAGE — Matches (D5/D6)
SORT_OPTIONS = [
    "Best match",
    "Price ↑ (low to high)",
    "Price ↓ (high to low)",
    "Size ↑ (small to large)",
    "Size ↓ (large to small)",
]
# Short codes <-> options, so the Sort dropdown and clickable table headers share one
# state via the ?sort= query param (no widget-vs-URL conflict).
_SORT_CODES = {
    "Best match": "best",
    "Price ↑ (low to high)": "price_asc",
    "Price ↓ (high to low)": "price_desc",
    "Size ↑ (small to large)": "size_asc",
    "Size ↓ (large to small)": "size_desc",
}
_CODE_TO_OPT = {v: k for k, v in _SORT_CODES.items()}

# "Show" filter <-> codes (URL state).
SHOW_OPTIONS = ["👍 Liked & new", "👍 Liked", "🆕 Unrated", "👎 Passed", "All"]
_SHOW_CODES = {"👍 Liked & new": "liked_new", "👍 Liked": "liked",
               "🆕 Unrated": "unrated", "👎 Passed": "passed", "All": "all"}
_CODE_TO_SHOW = {v: k for k, v in _SHOW_CODES.items()}


def _build_qs(state: dict, **override) -> str:
    """Query string from the page state (+ overrides). Used for every in-HTML link so a
    click preserves view/requirement/show/sort and the page survives a reload (D-UI)."""
    return urllib.parse.urlencode({**state, **{k: v for k, v in override.items()
                                               if v is not None}})


def _apply_sort(rows: list[dict], choice: str) -> list[dict]:
    """Sort listing dicts by the chosen option. None values always sort last,
    regardless of direction. Never crashes on missing/None price/size/score."""
    def asc(field):
        # (None last, value) — Nones group to the end for ascending order.
        return lambda m: (m.get(field) is None, m.get(field))

    def desc(field):
        # Keep Nones last by sorting on (None last, -value) for present values.
        return lambda m: (m.get(field) is None, -(m.get(field) or 0))

    if choice == "Price ↑ (low to high)":
        return sorted(rows, key=asc("price"))
    if choice == "Price ↓ (high to low)":
        return sorted(rows, key=desc("price"))
    if choice == "Size ↑ (small to large)":
        return sorted(rows, key=asc("size_sqm"))
    if choice == "Size ↓ (large to small)":
        return sorted(rows, key=desc("size_sqm"))
    # "Best match" (default): score desc, None last.
    return sorted(rows, key=desc("score"))


def _sync(param: str, value: str) -> None:
    """Write a control's value to the URL so reloads/clicks keep it (idempotent)."""
    if st.query_params.get(param) != value:
        st.query_params[param] = value


def page_matches():
    qp = st.query_params
    # View toggle sits inline with the heading, right-aligned (icon segmented control).
    # Every control below derives its default from the URL, so a reload restores the
    # exact view + filters (D-UI).
    view_default = qp.get("view") if qp.get("view") in ("Cards", "Table") else "Cards"
    hc1, hc2 = st.columns([3, 1], vertical_alignment="center")
    with hc1:
        _header("Matches", "Listings ranked by how well they fit your requirements.")
    with hc2:
        view = st.segmented_control(
            "View", ["Cards", "Table"], default=view_default,
            format_func=lambda v: {"Cards": "▦ Cards", "Table": "☰ Table"}[v],
            label_visibility="collapsed", key="match_view") or "Cards"
    _sync("view", view)

    # TODO: a list_matches() in db.py would let us show notified matches too.
    matches = db.unnotified_matches()
    if not matches:
        _empty_state(
            "🔍", "No matches yet",
            "Add a requirement on the <b>Requirements</b> page, then hit "
            "<b>🔄 Refresh listings now</b> in the sidebar to scrape the portals "
            "and find homes that fit.")
        return

    # One compact dropdown for requirement — shows a readable summary (owner/type/size/budget).
    _reqs = {r["id"]: r for r in db.list_requirements()}
    req_ids = sorted({m["requirement_id"] for m in matches})
    req_options = ["All"] + req_ids
    _rp = qp.get("req")
    _req_idx = 0
    if _rp and _rp != "All":
        try:
            _req_idx = req_options.index(int(_rp))
        except (ValueError, IndexError):
            _req_idx = 0
    # Per-sector listing counts, shown in the multiselect labels (e.g. "Sector 50 (12)").
    _sec_counts = Counter(
        matcher._sector_num(m.get("sector")) for m in matches
        if matcher._sector_num(m.get("sector")))
    sector_opts = sorted(_sec_counts, key=int)
    _sec_default = [s for s in (qp.get("sec") or "").split(",") if s in sector_opts]

    # All filters on one row: Requirement · Show · Sort · Sectors · Group toggle.
    f1, f2, f3, f4, f5 = st.columns([3, 2, 2, 3, 1.5], vertical_alignment="bottom")
    req_filter = f1.selectbox(
        "Requirement", req_options, index=_req_idx,
        format_func=lambda r: "All requirements" if r == "All"
        else (_requirement_summary(_reqs[r]) if r in _reqs else f"#{r}"))
    req_code = "All" if req_filter == "All" else str(req_filter)
    _sync("req", req_code)

    show_default = _CODE_TO_SHOW.get(qp.get("show"), SHOW_OPTIONS[0])
    show_filter = f2.selectbox("Show", SHOW_OPTIONS,
                               index=SHOW_OPTIONS.index(show_default))
    _sync("show", _SHOW_CODES[show_filter])

    # Sort is shared with the clickable table headers via ?sort=<code>.
    sort_default = _CODE_TO_OPT.get(qp.get("sort"), SORT_OPTIONS[0])
    sort_choice = f3.selectbox("Sort", SORT_OPTIONS,
                               index=SORT_OPTIONS.index(sort_default))
    sort_code = _SORT_CODES[sort_choice]
    _sync("sort", sort_code)

    sel_sectors = f4.multiselect(
        "Sectors", sector_opts, default=_sec_default,
        format_func=lambda s: f"Sector {s} ({_sec_counts[s]})",
        placeholder="All sectors")
    _sync("sec", ",".join(sel_sectors))
    group_by = f5.toggle("🗂 Group", value=qp.get("grp") == "1",
                         help="Group listings by sector")
    _sync("grp", "1" if group_by else "0")

    state = {"pg": "Matches", "view": view, "req": req_code,
             "show": _SHOW_CODES[show_filter], "sort": sort_code,
             "sec": ",".join(sel_sectors), "grp": "1" if group_by else "0"}

    rows = matches
    noida_on = bool(db.get_setting("noida_authority_only", 1))
    if noida_on:  # D21
        rows = [m for m in rows if db.is_noida_authority(m)]
    dropped_by_noida = len(matches) - len(rows)
    # Hard sector filter (D24): drop matches whose listing isn't in that requirement's
    # chosen sectors (handles old matches recorded before sectors were set).
    _req_sectors = {r["id"]: (r["sectors"] or []) for r in db.list_requirements()}
    before_sector = len(rows)
    rows = [m for m in rows
            if matcher.sector_matches(m.get("sector"),
                                      _req_sectors.get(m["requirement_id"], []))]
    dropped_by_sector = before_sector - len(rows)
    if req_filter != "All":
        rows = [m for m in rows if m["requirement_id"] == req_filter]
    # Filter by the user's like/pass verdict per the "Show" selector.
    _fb = db.feedback_map()
    _keep = {
        "👍 Liked & new": lambda v: v != "nope",
        "👍 Liked": lambda v: v == "like",
        "🆕 Unrated": lambda v: v is None,
        "👎 Passed": lambda v: v == "nope",
        "All": lambda v: True,
    }[show_filter]
    rows = [m for m in rows if _keep(_fb.get(m.get("id")))]
    if sel_sectors:  # explicit sector filter (in addition to the per-requirement one)
        rows = [m for m in rows
                if matcher._sector_num(m.get("sector")) in sel_sectors]
    rows = _apply_sort(rows, sort_choice)

    if not rows:
        # Common cause: not logged in -> HTML-only listings have no authority data ->
        # the Noida filter hides them all. Tell the user exactly what to do (D21/D22).
        bits = []
        if dropped_by_sector:
            bits.append(f"{dropped_by_sector} outside your chosen sectors")
        if noida_on and dropped_by_noida:
            bits.append(f"{dropped_by_noida} not NOIDA-Authority/freehold")
        if bits:
            _empty_state(
                "🪄", "Everything got filtered out",
                "Hidden by your filters (" + html.escape("; ".join(bits)) + "). "
                "Widen the sectors or budget on the <b>Requirements</b> page, ease "
                "the rules in <b>Settings</b>, or <b>🔄 Refresh</b> for fresh listings.")
        else:
            _empty_state(
                "🧭", "Nothing for these filters",
                "No matches for the selected owner / requirement. Try "
                "<b>All owners</b> and <b>All requirements</b>.")
        return

    _render_listings(rows, view, state, sort_code, group_by_sector=group_by)


def _render_listings(rows: list[dict], view: str, state: dict,
                     sort_code: str = "best", group_by_sector: bool = False) -> None:
    """Render a list of listing/match dicts as cards or table + the lightbox gallery.
    Shared by Matches and Shortlist. `state` is carried in every in-HTML link so a click
    preserves the view + all filters. When group_by_sector is set, rows are split into
    per-sector sections each with a heading."""
    # Index listings that have an image, in display order, so the photo click opens
    # #lb<k> and prev/next walk across all properties (index spans ALL rows, so the
    # gallery still works across sector groups).
    imaged = [m for m in rows if m.get("image_url")]
    lb_index = {id(m): k for k, m in enumerate(imaged)}
    lb_of = lambda m: lb_index.get(id(m))  # noqa: E731
    fb = db.feedback_map()
    fb_of = lambda m: fb.get(m.get("id"))  # noqa: E731
    reasons = db.feedback_reasons()
    reason_of = lambda m: reasons.get(m.get("id"))  # noqa: E731
    track = db.tracking_map()
    track_of = lambda m: track.get(m.get("id"))  # noqa: E731
    # Flag listings first seen in the most recent scrape run as "new" (D31).
    _runs = db.recent_runs(1)
    _since = _runs[0].get("started_at") if _runs else None
    for _m in rows:
        _m["__new__"] = bool(_since and (_m.get("first_seen_at") or "") >= _since)
    gallery = _lightbox_html(imaged, fb_of, state, reason_of, track_of)

    def _block(block_rows: list[dict]) -> str:
        if view == "Cards":
            cards = "".join(
                _match_card_html(m, lb_of(m), fb_of(m), state, reason_of(m), track_of(m))
                for m in block_rows)
            return f"<div class='ps-grid'>{cards}</div>"
        return _match_table_html(block_rows, lb_of, fb_of, state, sort_code,
                                 reason_of, track_of)

    if group_by_sector:
        groups: dict[str, list[dict]] = {}
        for m in rows:
            key = matcher._sector_num(m.get("sector")) or "—"
            groups.setdefault(key, []).append(m)
        order = sorted(groups, key=lambda k: (k == "—", int(k) if k.isdigit() else 1e9))
        parts = []
        for k in order:
            grp = groups[k]
            label = f"Sector {k}" if k != "—" else "Other"
            parts.append(
                "<div class='ps-sec-group'>"
                f"<div class='ps-sec-h'>📍 {html.escape(label)}"
                f"<span class='ps-sec-n'>{len(grp)}</span></div>"
                f"{_block(grp)}</div>")
        st.markdown("".join(parts) + gallery, unsafe_allow_html=True)
        return

    st.markdown(_block(rows) + gallery, unsafe_allow_html=True)


def _render_followups(state: dict) -> None:
    """Native follow-up tracker (D29): every liked or contacted listing, each with a
    contacted toggle + an editable notes box. The one place notes are edited (the bulk
    HTML cards can't host Streamlit text inputs)."""
    tm = db.tracking_map()
    items, seen = [], set()
    for m in db.list_contacted() + db.list_feedback("like"):
        if m["id"] not in seen:
            items.append(m)
            seen.add(m["id"])
    if not items:
        _empty_state("📞", "No follow-ups yet",
                     "Tap <b>📞 Mark contacted</b> or <b>👍 Like</b> on a listing, then "
                     "track your calls and notes here.")
        return
    for m in items:
        tr = tm.get(m["id"], {})
        contacted_on = tr.get("contacted_at")
        with st.container(border=True, key=f"followcard_{m['id']}"):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            with c1:
                title = m.get("title") or "Untitled listing"
                url = m.get("url")
                st.markdown(f"**[{title}]({url})**" if url else f"**{title}**")
                bits = []
                if m.get("price"):
                    bits.append(f"₹ {rupees_to_cr(m['price']):g} Cr")
                if m.get("sector"):
                    bits.append(f"📍 Sector {m['sector']}")
                if contacted_on:
                    bits.append("✅ Contacted " + str(contacted_on)[:16].replace("T", " "))
                if bits:
                    st.caption(" · ".join(bits))
            with c2:
                lbl = "↩︎ Undo" if contacted_on else "📞 Contacted"
                if st.button(lbl, key=f"contact_{m['id']}", use_container_width=True):
                    db.set_contacted(m["id"])
                    st.rerun()
            note = st.text_area(
                "Notes", value=tr.get("notes") or "", key=f"note_{m['id']}",
                label_visibility="collapsed", height=72,
                placeholder="Follow-up notes — asking price, broker name, next step…")
            if note != (tr.get("notes") or ""):
                db.set_note(m["id"], note)


def page_shortlist():
    _header("Shortlist", "Homes you reacted to. Liked ones are kept here so you can "
            "follow up later — even after they leave the Matches view.")
    liked = db.list_feedback("like")
    passed = db.list_feedback("nope")
    contacted = db.list_contacted()
    sort_default = _CODE_TO_OPT.get(st.query_params.get("sort"), SORT_OPTIONS[0])
    sort_choice = st.selectbox("Sort", SORT_OPTIONS,
                               index=SORT_OPTIONS.index(sort_default))
    _sync("sort", _SORT_CODES[sort_choice])
    state = {"pg": "Shortlist", "sort": _SORT_CODES[sort_choice]}
    liked = _apply_sort(liked, sort_choice)
    passed = _apply_sort(passed, sort_choice)
    n_follow = len({m["id"] for m in contacted} | {m["id"] for m in liked})
    t1, t2, t3 = st.tabs([f"👍 Liked · {len(liked)}", f"👎 Passed · {len(passed)}",
                          f"📞 Follow-ups · {n_follow}"])
    with t1:
        if liked:
            _render_listings(liked, "Cards", state)
        else:
            _empty_state("💚", "No liked homes yet",
                         "Open <b>Matches</b> and tap <b>👍</b> on the ones you like — "
                         "they'll collect here for follow-up.")
    with t2:
        if passed:
            _render_listings(passed, "Cards", state)
        else:
            _empty_state("🗂️", "Nothing passed yet",
                         "Homes you mark <b>👎</b> show up here, out of your way.")
    with t3:
        _render_followups(state)


# ============================================================== PAGE — System (D15)
def _tile(label: str, value, accent: str = "") -> str:
    """One stat tile. accent ∈ {'', 'ok', 'warn', 'bad'} drives the side bar + value colour."""
    tcls = f" ps-tile-{accent}" if accent else ""
    vcls = f" ps-v-{accent}" if accent else ""
    return (f"<div class='ps-tile{tcls}'>"
            f"<div class='ps-tile-lbl'>{html.escape(label)}</div>"
            f"<div class='ps-tile-val{vcls}'>{html.escape(str(value))}</div></div>")


def _fmt_ts(ts) -> str:
    """Trim a stored timestamp to a compact, scannable form (drop microseconds)."""
    if not ts:
        return ""
    s = str(ts)
    return s.split(".")[0]


def page_system():
    _header("System", "Health of the unattended 6-hour pipeline.")
    summary = db.status_summary()
    totals = summary.get("totals", {})
    raw = summary.get("raw_health", {})

    stale = int(totals.get("stale_listings", 0) or 0)
    unnot = int(totals.get("unnotified_matches", 0) or 0)
    errs = int(raw.get("error", 0) or 0)

    # ---- top-line + pipeline tiles (single compact row, semantic accents) ----
    st.markdown("<div class='ps-section'>Overview</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ps-tilerow'>"
        + _tile("Active listings", totals.get("active_listings", 0), "ok")
        + _tile("Stale listings", stale, "warn" if stale else "")
        + _tile("Total matches", totals.get("total_matches", 0))
        + _tile("Un-notified", unnot, "warn" if unnot else "")
        + "</div>",
        unsafe_allow_html=True)

    st.markdown("<div class='ps-section'>Pipeline health</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ps-tilerow'>"
        + _tile("Pending parse", raw.get("pending", 0))
        + _tile("Parsed", raw.get("parsed", 0), "ok")
        + _tile("Parse errors", errs, "bad" if errs else "ok")
        + "</div>",
        unsafe_allow_html=True)

    # ---- portals ----
    st.markdown("<div class='ps-section'>Portals</div>", unsafe_allow_html=True)
    portals = summary.get("portals", [])
    if portals:
        cards = "".join(
            f"<div class='ps-portal'>"
            f"<div class='ps-portal-head'>"
            f"<span class='ps-portal-name'>🌐 {html.escape(p.get('name', ''))}</span>"
            + ("<span class='ps-stat ps-stat-on'>● Enabled</span>" if p.get("enabled")
               else "<span class='ps-stat ps-stat-off'>○ Disabled</span>")
            + "</div>"
            f"<div class='ps-portal-meta'>Last run: "
            f"<b>{html.escape(_fmt_ts(p.get('last_run_at')) or 'never')}</b></div>"
            "</div>"
            for p in portals)
        st.markdown(f"<div class='ps-portalrow'>{cards}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='ps-ok-state'>No portals configured yet.</div>",
                    unsafe_allow_html=True)

    # ---- recent parse errors ----
    st.markdown("<div class='ps-section'>Recent parse errors</div>",
                unsafe_allow_html=True)
    errors = summary.get("recent_errors", [])
    if errors:
        items = "".join(
            f"<div class='ps-err'>"
            f"<div class='ps-err-url'>{html.escape(str(e.get('url') or '—'))}</div>"
            f"<div class='ps-err-msg'>{html.escape(str(e.get('parse_error') or ''))}</div>"
            "</div>"
            for e in errors)
        st.markdown(f"<div class='ps-errlist'>{items}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='ps-ok-state'>✓ No recent parse errors.</div>",
                    unsafe_allow_html=True)

    # ---- run history (styled table, no horizontal scroll) ----
    st.markdown("<div class='ps-section'>Run history</div>", unsafe_allow_html=True)
    runs = db.recent_runs(20)
    if not runs:
        st.markdown("<div class='ps-ok-state' style='background:#eef2ff;border-color:"
                    "#c7d2fe;color:#4338ca;'>No runs recorded yet.</div>",
                    unsafe_allow_html=True)
        return

    # 7 fields → compact columns; "started" gets the most room, numbers stay narrow.
    cols_w = [2.1, 2.1, 1.0, 1.0, 1.1, 1.0, 1.1]
    heads = ["Started", "Finished", "Fetched", "Parsed", "Errors", "Matches", "Notified"]
    with st.container(key="runtable"):
        h = st.columns(cols_w, vertical_alignment="center")
        for col, lbl in zip(h, heads):
            col.markdown(f"<div class='ps-th-c'>{lbl}</div>", unsafe_allow_html=True)
        for r in runs:
            row = st.columns(cols_w, vertical_alignment="center")
            row[0].markdown(
                f"<div class='ps-td-c'>{html.escape(_fmt_ts(r.get('started_at')))}</div>",
                unsafe_allow_html=True)
            fin = _fmt_ts(r.get("finished_at"))
            row[1].markdown(
                f"<div class='ps-td-c'>{html.escape(fin)}</div>" if fin
                else "<div class='ps-td-c ps-td-mut'>running…</div>",
                unsafe_allow_html=True)

            def _num(v, bad=False):
                v = v or 0
                if bad and v:
                    return f"<div class='ps-td-c ps-num-bad'>{v}</div>"
                cls = "ps-num-zero" if not v else ""
                return f"<div class='ps-td-c {cls}'>{v}</div>"

            row[2].markdown(_num(r.get("raw_fetched")), unsafe_allow_html=True)
            row[3].markdown(_num(r.get("parsed_ok")), unsafe_allow_html=True)
            row[4].markdown(_num(r.get("parse_errors"), bad=True),
                            unsafe_allow_html=True)
            row[5].markdown(_num(r.get("new_matches")), unsafe_allow_html=True)
            row[6].markdown(_num(r.get("notified")), unsafe_allow_html=True)


# ============================================================== PAGE — Settings (D17)
def page_settings():
    _header("Settings", "Control how listings are scored and matched. "
                        "Plain-English knobs — changes apply on the next refresh.")
    knobs = db.all_settings()

    st.caption("💡 Every listing gets a **match score** from 0–100%. These settings decide "
               "how that score is calculated and how strict the cut-off is. "
               "Not sure? The defaults work well — use **Reset to defaults** anytime.")

    with st.form("settings_form"):
        # ---- 1. Strictness -------------------------------------------------------
        st.subheader("1 · How strict should matching be?")
        threshold_pct = st.slider(
            "Only show listings scoring at least this high", 0, 100,
            int(round(float(knobs.get("threshold", 0.6)) * 100)), 5, format="%d%%")
        st.caption(f"Right now a listing needs **≥ {threshold_pct}%** to appear. "
                   "Higher = fewer but better-fitting results; lower = more results, "
                   "some loose.")

        st.divider()
        # ---- 2. What matters most ------------------------------------------------
        st.subheader("2 · What matters most in a good match?")
        st.caption("Set how much each factor counts. The exact numbers don't need to add "
                   "up — we rebalance them to 100% for you (shown below).")
        wc1, wc2, wc3 = st.columns(3)
        w_size = wc1.slider("Right size", 0.0, 1.0,
                            float(knobs.get("w_size", 0.4)), 0.05,
                            help="How close the listing's area is to your target size.")
        w_price = wc2.slider("Right price", 0.0, 1.0,
                             float(knobs.get("w_price", 0.4)), 0.05,
                             help="How well the price fits your budget.")
        w_sector = wc3.slider("Right location", 0.0, 1.0,
                              float(knobs.get("w_sector", 0.2)), 0.05,
                              help="Whether it's in one of your chosen sectors.")
        w_sum = w_size + w_price + w_sector
        if w_sum > 0:
            st.caption(f"➡️ Balance used: **Size {w_size / w_sum:.0%} · "
                       f"Price {w_price / w_sum:.0%} · Location {w_sector / w_sum:.0%}**")
        else:
            st.warning("Set at least one factor above zero.")

        st.divider()
        # ---- 3. How forgiving -----------------------------------------------------
        st.subheader("3 · How forgiving should it be?")
        over_budget_pct = st.slider(
            "Allow listings priced over budget by up to…", 0, 50,
            int(round(float(knobs.get("budget_softcap_pct", 0.05)) * 100)), 1,
            format="%d%%")
        st.caption(f"A listing up to **{over_budget_pct}% above** your max budget can still "
                   "appear (ranked lower). E.g. {over} on a ₹4.50 Cr budget."
                   .format(over=f"₹{4.5 * (1 + over_budget_pct / 100):.2f} Cr"))

        outside_sector_pct = st.slider(
            "Credit for listings outside your chosen sectors", 0, 100,
            int(round(float(knobs.get("sector_miss_fit", 0.3)) * 100)), 5, format="%d%%")
        st.caption(f"A listing in a sector you didn't pick still earns **{outside_sector_pct}%** "
                   "on the location factor. 0% = your sectors only; higher = nearby "
                   "sectors keep showing. (No sectors chosen = everywhere counts fully.)")

        wrong_type_choice = st.radio(
            "Listings of a different property type than you asked for",
            ["Hide them completely (recommended)", "Show them, but rank them low"],
            index=0 if float(knobs.get("type_miss_fit", 0.0)) == 0 else 1,
            help="E.g. a Plot showing up in a House search.")

        noida_only = st.checkbox(
            "Only Noida-Authority sectors & plots (exclude freehold / other authorities)",
            value=bool(knobs.get("noida_authority_only", 1)),
            help="Noida-Authority allotments are leasehold and sit in numbered Noida "
                 "sectors. Unchecking also lets in freehold private colonies, YEIDA, "
                 "Greater Noida, etc.")

        st.divider()
        # ---- 4. Freshness ---------------------------------------------------------
        st.subheader("4 · When is a listing 'gone'?")
        stale_runs = st.slider(
            "Hide a listing after it's missing for this many refresh cycles", 1, 12,
            int(knobs.get("stale_threshold_runs", 3)), 1)
        st.caption(f"One cycle = 6 hours, so this hides listings unseen for about "
                   f"**{stale_runs * 6 / 24:.1f} days**.")

        st.write("")
        c1, c2 = st.columns([1, 1])
        save = c1.form_submit_button("💾 Save settings", type="primary",
                                     use_container_width=True)
        reset = c2.form_submit_button("↩️ Reset to defaults", use_container_width=True)

    if save:
        # Normalize the importance sliders to sum to 1.0 (the matcher + threshold are
        # calibrated for that), so the user never has to make them add up.
        total = w_size + w_price + w_sector or 1.0
        for key, value in {
            "threshold": threshold_pct / 100,
            "w_size": w_size / total, "w_price": w_price / total,
            "w_sector": w_sector / total,
            "budget_softcap_pct": over_budget_pct / 100,
            "sector_miss_fit": outside_sector_pct / 100,
            "type_miss_fit": 0.0 if wrong_type_choice.startswith("Hide") else 0.3,
            "noida_authority_only": 1 if noida_only else 0,
            "stale_threshold_runs": stale_runs,
        }.items():
            db.set_setting(key, value)
        st.success("Saved. Applies on the next refresh / scheduled run.")
        st.rerun()
    if reset:
        for key, value in db.SEED_SETTINGS.items():
            db.set_setting(key, value)
        st.success("Settings reset to defaults.")
        st.rerun()


# ----------------------------------------------------------------------------- dispatch
if PAGE == "Requirements":
    page_requirements()
elif PAGE == "Matches":
    page_matches()
elif PAGE == "Shortlist":
    page_shortlist()
elif PAGE == "System":
    page_system()
else:
    page_settings()
