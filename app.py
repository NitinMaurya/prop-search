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

import html

import streamlit as st

import db

CR = 10_000_000  # 1 Crore = 10,000,000 rupees (D9 budget display convenience)
SIZE_OPTIONS = [112, 162]  # confirmed target sizes (Q2); custom allowed via number input


def rupees_to_cr(rupees) -> float:
    return round((rupees or 0) / CR, 4)


def cr_to_rupees(cr) -> int:
    return int(round((cr or 0) * CR))


# ------------------------------------------------------------------------- page styling
def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}
        #MainMenu, footer {visibility: hidden;}

        .ps-h1 {font-size: 1.85rem; font-weight: 750; margin: 0 0 .1rem; color:#0f172a;}
        .ps-sub {color:#64748b; font-size:.95rem; margin: 0 0 1.3rem;}

        /* metric tiles */
        div[data-testid="stMetric"] {background:#f8fafc; border:1px solid #e2e8f0;
            border-radius:14px; padding:14px 18px;}
        div[data-testid="stMetricValue"] {font-size:1.6rem;}

        /* cards */
        .ps-card {background:#fff; border:1px solid #e5e7eb; border-radius:16px;
            padding:18px 20px; margin-bottom:14px; box-shadow:0 1px 3px rgba(16,24,40,.05);}
        .ps-card-head {display:flex; justify-content:space-between; align-items:flex-start;
            gap:12px;}
        .ps-title {font-size:1.05rem; font-weight:650; color:#0f172a; line-height:1.35;}
        .ps-price {font-size:1.55rem; font-weight:780; color:#1d4ed8; margin:.4rem 0 .6rem;}
        .ps-chips {display:flex; flex-wrap:wrap; gap:8px; margin-bottom:.85rem;}
        .ps-chip {background:#f1f5f9; color:#334155; border-radius:999px; padding:4px 12px;
            font-size:.82rem; font-weight:550;}
        .ps-badge {border-radius:999px; padding:6px 13px; font-weight:750; font-size:.85rem;
            white-space:nowrap;}
        .ps-hi {background:#dcfce7; color:#15803d;}
        .ps-mid {background:#fef9c3; color:#a16207;}
        .ps-lo {background:#e2e8f0; color:#475569;}
        .ps-btn {display:inline-block; background:#1d4ed8; color:#fff !important;
            text-decoration:none; padding:8px 16px; border-radius:10px; font-weight:600;
            font-size:.86rem;}
        .ps-btn:hover {background:#1e40af;}
        .ps-pill {border-radius:999px; padding:3px 11px; font-size:.8rem; font-weight:650;}
        .ps-ok {background:#dcfce7; color:#15803d;}
        .ps-bad {background:#fee2e2; color:#b91c1c;}
        .ps-muted {background:#e2e8f0; color:#475569;}

        /* sidebar brand */
        .ps-brand {font-size:1.35rem; font-weight:800; color:#1d4ed8; margin:.2rem 0 0;}
        .ps-brand-sub {color:#64748b; font-size:.8rem; margin:0 0 .6rem;}
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


# Initialise schema once per process (idempotent — safe on every rerun).
db.init()
st.set_page_config(page_title="prop-search", page_icon="🏡", layout="wide")
_inject_css()

# ------------------------------------------------------------------------------- sidebar
st.sidebar.markdown("<div class='ps-brand'>🏡 prop-search</div>"
                    "<div class='ps-brand-sub'>Noida kothi finder</div>",
                    unsafe_allow_html=True)
PAGE = st.sidebar.radio("Navigate", ["Matches", "Requirements", "System", "Settings"],
                        label_visibility="collapsed")

_sb = db.status_summary().get("totals", {})
st.sidebar.divider()
sb1, sb2 = st.sidebar.columns(2)
sb1.metric("Listings", _sb.get("active_listings", 0))
sb2.metric("Matches", _sb.get("total_matches", 0))
st.sidebar.caption("Run `python scheduler.py --once` to refresh listings.")


# ============================================================ PAGE — Requirements (D9)
def page_requirements():
    _header("Requirements", "Your saved property queries. The scheduler checks every "
                            "active one each run.")

    with st.expander("➕ Add a requirement", expanded=not db.list_requirements()):
        with st.form("create_requirement", clear_on_submit=True):
            c1, c2 = st.columns(2)
            owner = c1.text_input("Owner (name/email) *")
            property_type = c2.text_input("Property type", value="kothi")

            c3, c4 = st.columns(2)
            sizes_sel = c3.multiselect("Sizes (sqm)", options=SIZE_OPTIONS,
                                       default=SIZE_OPTIONS)
            custom_size = c4.number_input("Add custom size (sqm)", min_value=0,
                                          step=1, value=0)

            c5, c6, c7 = st.columns(3)
            budget_min_cr = c5.number_input("Budget min (Cr)", min_value=0.0,
                                            value=4.0, step=0.1)
            budget_max_cr = c6.number_input("Budget max (Cr)", min_value=0.0,
                                            value=4.5, step=0.1)
            size_tolerance_pct = c7.number_input("Size tolerance (%)", min_value=0.0,
                                                 value=30.0, step=1.0)

            sectors_raw = st.text_input("Sectors (comma-separated; empty = all Noida)")
            submitted = st.form_submit_button("Create requirement", type="primary")

        if submitted:
            if not owner.strip():
                st.error("Owner is required.")
            else:
                sizes = list(dict.fromkeys(sizes_sel + ([int(custom_size)]
                                                         if custom_size else [])))
                sectors = [s.strip() for s in sectors_raw.split(",") if s.strip()]
                db.add_requirement(
                    owner=owner.strip(),
                    budget_min=cr_to_rupees(budget_min_cr),
                    budget_max=cr_to_rupees(budget_max_cr),
                    sizes_sqm=sizes, sectors=sectors,
                    property_type=property_type.strip() or "kothi",
                    size_tolerance_pct=size_tolerance_pct,
                )
                st.success(f"Added requirement for {owner.strip()}.")
                st.rerun()

    reqs = db.list_requirements()
    if not reqs:
        st.info("No requirements yet — add one above to start matching.")
        return

    for r in reqs:
        sizes_disp = ", ".join(str(s) for s in r["sizes_sqm"]) or "—"
        sectors_disp = ", ".join(r["sectors"]) if r["sectors"] else "all Noida"
        pill = ("<span class='ps-pill ps-ok'>active</span>" if r["active"]
                else "<span class='ps-pill ps-muted'>inactive</span>")
        st.markdown(
            f"<div class='ps-card'><div class='ps-card-head'>"
            f"<div class='ps-title'>#{r['id']} · {html.escape(r['owner'])} · "
            f"{html.escape(r['property_type'])}</div>{pill}</div>"
            f"<div class='ps-chips'>"
            f"<span class='ps-chip'>📐 {sizes_disp} sqm (±{r['size_tolerance_pct']:g}%)</span>"
            f"<span class='ps-chip'>💰 {rupees_to_cr(r['budget_min'])}–"
            f"{rupees_to_cr(r['budget_max'])} Cr</span>"
            f"<span class='ps-chip'>📍 {html.escape(sectors_disp)}</span>"
            f"</div></div>", unsafe_allow_html=True)

        with st.expander(f"Edit / manage #{r['id']}"):
            with st.form(f"edit_requirement_{r['id']}"):
                ec1, ec2 = st.columns(2)
                owner_e = ec1.text_input("Owner", value=r["owner"], key=f"o_{r['id']}")
                ptype_e = ec2.text_input("Property type", value=r["property_type"],
                                         key=f"pt_{r['id']}")
                sizes_e = st.text_input("Sizes (sqm, comma-separated)",
                                        value=", ".join(str(s) for s in r["sizes_sqm"]),
                                        key=f"sz_{r['id']}")
                ec3, ec4, ec5 = st.columns(3)
                bmin_e = ec3.number_input("Budget min (Cr)", min_value=0.0,
                                          value=rupees_to_cr(r["budget_min"]), step=0.1,
                                          key=f"bn_{r['id']}")
                bmax_e = ec4.number_input("Budget max (Cr)", min_value=0.0,
                                          value=rupees_to_cr(r["budget_max"]), step=0.1,
                                          key=f"bx_{r['id']}")
                tol_e = ec5.number_input("Tolerance (%)", min_value=0.0,
                                         value=float(r["size_tolerance_pct"]), step=1.0,
                                         key=f"tl_{r['id']}")
                sectors_e = st.text_input("Sectors (comma-separated; empty = all Noida)",
                                          value=", ".join(r["sectors"]),
                                          key=f"sc_{r['id']}")
                active_e = st.checkbox("Active", value=bool(r["active"]),
                                       key=f"ac_{r['id']}")
                bc1, bc2 = st.columns(2)
                save = bc1.form_submit_button("Save changes", type="primary")
                deactivate = bc2.form_submit_button("Deactivate")

            if save:
                sizes = []
                for tok in sizes_e.split(","):
                    tok = tok.strip()
                    if tok:
                        try:
                            sizes.append(int(float(tok)))
                        except ValueError:
                            st.warning(f"Ignored non-numeric size: {tok!r}")
                sectors = [s.strip() for s in sectors_e.split(",") if s.strip()]
                db.update_requirement(
                    r["id"], owner=owner_e.strip(),
                    property_type=ptype_e.strip() or "kothi", sizes_sqm=sizes,
                    size_tolerance_pct=tol_e, budget_min=cr_to_rupees(bmin_e),
                    budget_max=cr_to_rupees(bmax_e), sectors=sectors,
                    active=1 if active_e else 0)
                st.success(f"Updated requirement #{r['id']}.")
                st.rerun()
            if deactivate:
                db.deactivate_requirement(r["id"])
                st.success(f"Deactivated requirement #{r['id']}.")
                st.rerun()


# ============================================================== PAGE — Matches (D5/D6)
def page_matches():
    _header("Matches", "Listings ranked by how well they fit your requirements.")

    # TODO: a list_matches() in db.py would let us show notified matches too.
    matches = db.unnotified_matches()
    if not matches:
        st.info("No matches yet. Add a requirement, then run "
                "`python scheduler.py --once` to scrape and match.")
        return

    owners = sorted({m["owner"] for m in matches if m.get("owner")})
    req_ids = sorted({m["requirement_id"] for m in matches})
    f1, f2 = st.columns(2)
    owner_filter = f1.selectbox("Owner", ["All owners"] + owners)
    req_filter = f2.selectbox("Requirement", ["All requirements"] + req_ids)

    rows = matches
    if owner_filter != "All owners":
        rows = [m for m in rows if m.get("owner") == owner_filter]
    if req_filter != "All requirements":
        rows = [m for m in rows if m["requirement_id"] == req_filter]
    rows = sorted(rows, key=lambda m: m["score"] or 0, reverse=True)

    if not rows:
        st.info("No matches for the selected filters.")
        return

    prices = [m["price"] for m in rows if m.get("price")]
    s1, s2, s3 = st.columns(3)
    s1.metric("Matches", len(rows))
    s2.metric("Best score", f"{round((rows[0]['score'] or 0) * 100)}%")
    s3.metric("Lowest price", f"₹ {rupees_to_cr(min(prices))} Cr" if prices else "—")
    st.write("")

    for m in rows:
        title = html.escape(m.get("title") or "(untitled listing)")
        price_cr = rupees_to_cr(m.get("price"))
        size = m.get("size_sqm")
        size_disp = f"{size:g}" if size is not None else "—"
        sector = html.escape(m.get("sector") or "—")
        owner = html.escape(m.get("owner") or "—")
        pct = round((m.get("score") or 0) * 100)
        url = m.get("url") or ""
        btn = (f"<a class='ps-btn' href='{html.escape(url)}' target='_blank'>"
               f"View listing ↗</a>") if url else ""
        st.markdown(
            f"<div class='ps-card'>"
            f"<div class='ps-card-head'><div class='ps-title'>{title}</div>"
            f"<div class='ps-badge {_score_class(pct)}'>{pct}% match</div></div>"
            f"<div class='ps-price'>₹ {price_cr} Cr</div>"
            f"<div class='ps-chips'>"
            f"<span class='ps-chip'>📐 {size_disp} sqm</span>"
            f"<span class='ps-chip'>📍 {sector}</span>"
            f"<span class='ps-chip'>👤 {owner}</span>"
            f"<span class='ps-chip'>req #{m['requirement_id']}</span></div>"
            f"{btn}</div>", unsafe_allow_html=True)


# ============================================================== PAGE — System (D15)
def page_system():
    _header("System", "Health of the unattended 6-hour pipeline.")
    summary = db.status_summary()

    totals = summary.get("totals", {})
    t = st.columns(4)
    t[0].metric("Active listings", totals.get("active_listings", 0))
    t[1].metric("Stale listings", totals.get("stale_listings", 0))
    t[2].metric("Total matches", totals.get("total_matches", 0))
    t[3].metric("Un-notified", totals.get("unnotified_matches", 0))

    st.subheader("Pipeline health")
    raw = summary.get("raw_health", {})
    h = st.columns(3)
    h[0].metric("Pending", raw.get("pending", 0))
    h[1].metric("Parsed", raw.get("parsed", 0))
    h[2].metric("Errors", raw.get("error", 0))

    st.subheader("Portals")
    for p in summary.get("portals", []):
        pill = ("<span class='ps-pill ps-ok'>enabled</span>" if p.get("enabled")
                else "<span class='ps-pill ps-muted'>disabled</span>")
        last = p.get("last_run_at") or "never"
        st.markdown(
            f"<div class='ps-card' style='padding:12px 18px;'>"
            f"<div class='ps-card-head'><div class='ps-title'>{html.escape(p.get('name',''))}"
            f"</div>{pill}</div>"
            f"<div class='ps-chips' style='margin:.3rem 0 0;'>"
            f"<span class='ps-chip'>last run: {html.escape(str(last))}</span></div></div>",
            unsafe_allow_html=True)

    st.subheader("Recent parse errors")
    errors = summary.get("recent_errors", [])
    if errors:
        st.dataframe([{"url": e.get("url"), "error": e.get("parse_error")}
                      for e in errors], use_container_width=True, hide_index=True)
    else:
        st.success("No recent parse errors.")

    st.subheader("Run history")
    runs = db.recent_runs(20)
    if runs:
        st.dataframe(
            [{"started": r.get("started_at"),
              "finished": r.get("finished_at") or "(running)",
              "fetched": r.get("raw_fetched"), "parsed": r.get("parsed_ok"),
              "parse_errors": r.get("parse_errors"), "matches": r.get("new_matches"),
              "notified": r.get("notified")} for r in runs],
            use_container_width=True, hide_index=True)
    else:
        st.info("No runs recorded yet.")


# ============================================================== PAGE — Settings (D17)
def page_settings():
    _header("Settings", "Live matcher tuning. Saved to the DB; applied on the next run.")
    knobs = db.all_settings()

    with st.form("settings_form"):
        st.subheader("Match threshold")
        threshold = st.slider("Minimum score to count as a match", 0.0, 1.0,
                              float(knobs.get("threshold", 0.6)), 0.05)

        st.subheader("Scoring weights")
        wc1, wc2, wc3 = st.columns(3)
        w_size = wc1.slider("Size", 0.0, 1.0, float(knobs.get("w_size", 0.4)), 0.05)
        w_price = wc2.slider("Price", 0.0, 1.0, float(knobs.get("w_price", 0.4)), 0.05)
        w_sector = wc3.slider("Sector", 0.0, 1.0, float(knobs.get("w_sector", 0.2)), 0.05)
        w_sum = w_size + w_price + w_sector
        if abs(w_sum - 1.0) > 1e-6:
            st.warning(f"Weights sum to {w_sum:.2f} (ideal: 1.0). Scores may exceed 1; "
                       "the threshold is calibrated for a sum of 1.0.")
        else:
            st.caption("✓ Weights sum to 1.0")

        st.subheader("Tolerances & freshness")
        tc1, tc2 = st.columns(2)
        budget_softcap_pct = tc1.slider("Budget soft-cap (fraction over max)", 0.0, 0.5,
                                        float(knobs.get("budget_softcap_pct", 0.05)), 0.01)
        sector_miss_fit = tc2.slider("Wrong-sector score", 0.0, 1.0,
                                     float(knobs.get("sector_miss_fit", 0.3)), 0.05)
        stale_threshold_runs = st.number_input(
            "Stale after N missed 6h runs", min_value=1, step=1,
            value=int(knobs.get("stale_threshold_runs", 3)))

        if st.form_submit_button("Save settings", type="primary"):
            for key, value in {
                "threshold": threshold, "w_size": w_size, "w_price": w_price,
                "w_sector": w_sector, "budget_softcap_pct": budget_softcap_pct,
                "sector_miss_fit": sector_miss_fit,
                "stale_threshold_runs": stale_threshold_runs,
            }.items():
                db.set_setting(key, value)
            st.success("Saved. Applies on the next scheduler run.")
            st.rerun()


# ----------------------------------------------------------------------------- dispatch
if PAGE == "Requirements":
    page_requirements()
elif PAGE == "Matches":
    page_matches()
elif PAGE == "System":
    page_system()
else:
    page_settings()
