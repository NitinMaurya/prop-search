"""Streamlit UI — requirement form + matches dashboard + System/Status.

See docs/ARCHITECTURE.md. Four pages (sidebar radio): Requirements, Matches, System,
and Settings (live matcher tuning knobs from the DB, D17).
Legacy section map (sidebar radio):
  1. Requirements (build step 2): full CRUD — create / list / EDIT / deactivate
     (D9). Requirements are user data, never hardcoded; scheduler loops all active rows.
     Fields: owner (name/email), property_type (default "kothi"),
     sizes_sqm (multiselect 112/162 + custom), size_tolerance_pct (default 30),
     budget_min/max (4cr-4.5cr defaults), sectors (Noida).
  2. Matches dashboard (build step 4): ranked matches (score desc) with clickable
     listing URLs, price, size, sector, owner; filter by owner / requirement.
  3. System/Status (build step 7, D15): per-portal last-run + counts, pipeline health
     (raw_listings pending/parsed/error), recent parse errors w/ URL, totals
     (listings/stale/matches/un-notified), and run history from the `runs` table.
     Read-only — all queries against SQLite, no new infra.

Run: streamlit run app.py
"""

import streamlit as st

import db

CR = 10_000_000  # 1 Crore = 10,000,000 rupees (D9 budget display convenience)
SIZE_OPTIONS = [112, 162]  # confirmed target sizes (Q2); custom allowed via number input


def rupees_to_cr(rupees) -> float:
    return round((rupees or 0) / CR, 4)


def cr_to_rupees(cr) -> int:
    return int(round((cr or 0) * CR))


# Initialise schema once per process (idempotent — safe on every rerun).
db.init()

st.set_page_config(page_title="prop-search", layout="wide")
PAGE = st.sidebar.radio("Page", ["Requirements", "Matches", "System", "Settings"])


# ============================================================ PAGE 1 — Requirements (D9)
def page_requirements():
    st.title("Requirements")
    st.caption("User-defined queries. The scheduler loops over every active row (D9).")

    # ---- CREATE -------------------------------------------------------------------
    st.subheader("Add a requirement")
    with st.form("create_requirement", clear_on_submit=True):
        owner = st.text_input("Owner (name/email) *")
        property_type = st.text_input("Property type", value="kothi")

        sizes_sel = st.multiselect("Sizes (sqm)", options=SIZE_OPTIONS,
                                   default=SIZE_OPTIONS)
        custom_size = st.number_input("Add custom size (sqm, optional)", min_value=0,
                                      step=1, value=0)
        size_tolerance_pct = st.number_input("Size tolerance (%)", min_value=0.0,
                                              value=30.0, step=1.0)

        c1, c2 = st.columns(2)
        with c1:
            budget_min_cr = st.number_input("Budget min (Cr)", min_value=0.0,
                                            value=4.0, step=0.1)
        with c2:
            budget_max_cr = st.number_input("Budget max (Cr)", min_value=0.0,
                                            value=4.5, step=0.1)

        sectors_raw = st.text_input("Sectors (comma-separated; empty = all Noida)")
        submitted = st.form_submit_button("Create")

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
                sizes_sqm=sizes,
                sectors=sectors,
                property_type=property_type.strip() or "kothi",
                size_tolerance_pct=size_tolerance_pct,
            )
            st.success(f"Added requirement for {owner.strip()}.")
            st.rerun()

    st.divider()

    # ---- LIST / EDIT / DEACTIVATE -------------------------------------------------
    st.subheader("Existing requirements")
    reqs = db.list_requirements()
    if not reqs:
        st.info("No requirements yet. Add one above.")
        return

    for r in reqs:
        status = "active" if r["active"] else "inactive"
        sizes_disp = ", ".join(str(s) for s in r["sizes_sqm"]) or "-"
        sectors_disp = ", ".join(r["sectors"]) if r["sectors"] else "all Noida"
        header = (f"#{r['id']} · {r['owner']} · {r['property_type']} · "
                  f"{sizes_disp} sqm · "
                  f"{rupees_to_cr(r['budget_min'])}-{rupees_to_cr(r['budget_max'])} Cr "
                  f"· [{status}]")
        with st.expander(header, expanded=False):
            with st.form(f"edit_requirement_{r['id']}"):
                owner_e = st.text_input("Owner", value=r["owner"],
                                        key=f"owner_{r['id']}")
                ptype_e = st.text_input("Property type", value=r["property_type"],
                                        key=f"ptype_{r['id']}")
                sizes_e = st.text_input("Sizes (sqm, comma-separated)",
                                        value=", ".join(str(s) for s in r["sizes_sqm"]),
                                        key=f"sizes_{r['id']}")
                tol_e = st.number_input("Size tolerance (%)", min_value=0.0,
                                        value=float(r["size_tolerance_pct"]), step=1.0,
                                        key=f"tol_{r['id']}")
                c1, c2 = st.columns(2)
                with c1:
                    bmin_e = st.number_input(
                        "Budget min (Cr)", min_value=0.0,
                        value=rupees_to_cr(r["budget_min"]), step=0.1,
                        key=f"bmin_{r['id']}")
                with c2:
                    bmax_e = st.number_input(
                        "Budget max (Cr)", min_value=0.0,
                        value=rupees_to_cr(r["budget_max"]), step=0.1,
                        key=f"bmax_{r['id']}")
                sectors_e = st.text_input(
                    "Sectors (comma-separated; empty = all Noida)",
                    value=", ".join(r["sectors"]), key=f"sectors_{r['id']}")
                active_e = st.checkbox("Active", value=bool(r["active"]),
                                       key=f"active_{r['id']}")

                bc1, bc2 = st.columns(2)
                save = bc1.form_submit_button("Save changes")
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
                    r["id"],
                    owner=owner_e.strip(),
                    property_type=ptype_e.strip() or "kothi",
                    sizes_sqm=sizes,
                    size_tolerance_pct=tol_e,
                    budget_min=cr_to_rupees(bmin_e),
                    budget_max=cr_to_rupees(bmax_e),
                    sectors=sectors,
                    active=1 if active_e else 0,
                )
                st.success(f"Updated requirement #{r['id']}.")
                st.rerun()

            if deactivate:
                db.deactivate_requirement(r["id"])
                st.success(f"Deactivated requirement #{r['id']}.")
                st.rerun()


# ============================================================== PAGE 2 — Matches (D5/D6)
def page_matches():
    st.title("Matches")
    st.caption("Ranked by score. Showing un-notified matches (D5/D6).")

    # TODO: a list_matches() in db.py would let us show notified matches too.
    matches = db.unnotified_matches()

    if not matches:
        st.info("No matches yet. Once the scheduler runs, new matches appear here.")
        return

    # ---- filters ------------------------------------------------------------------
    owners = sorted({m["owner"] for m in matches if m.get("owner")})
    req_ids = sorted({m["requirement_id"] for m in matches})
    c1, c2 = st.columns(2)
    owner_filter = c1.selectbox("Filter by owner", ["(all)"] + owners)
    req_filter = c2.selectbox("Filter by requirement", ["(all)"] + req_ids)

    rows = matches
    if owner_filter != "(all)":
        rows = [m for m in rows if m.get("owner") == owner_filter]
    if req_filter != "(all)":
        rows = [m for m in rows if m["requirement_id"] == req_filter]

    rows = sorted(rows, key=lambda m: m["score"] or 0, reverse=True)

    if not rows:
        st.info("No matches for the selected filters.")
        return

    st.write(f"**{len(rows)}** match(es).")
    for m in rows:
        title = m.get("title") or "(untitled listing)"
        price_cr = rupees_to_cr(m.get("price"))
        size = m.get("size_sqm")
        sector = m.get("sector") or "-"
        score_pct = round((m.get("score") or 0) * 100)
        url = m.get("url")

        with st.container(border=True):
            top = st.columns([4, 1])
            top[0].markdown(f"### {title}")
            top[1].metric("Score", f"{score_pct}%")
            info = st.columns(4)
            info[0].markdown(f"**Price**  \n₹ {price_cr} Cr")
            info[1].markdown(f"**Size**  \n{size if size is not None else '-'} sqm")
            info[2].markdown(f"**Sector**  \n{sector}")
            info[3].markdown(f"**Owner**  \n{m.get('owner') or '-'}")
            st.caption(f"Requirement #{m['requirement_id']}")
            if url:
                st.markdown(f"[Open listing]({url})")


# ============================================================== PAGE 3 — System (D15)
def page_system():
    st.title("System / Status")
    st.caption("Observability for the unattended 6h pipeline (D15).")

    summary = db.status_summary()

    # ---- totals -------------------------------------------------------------------
    totals = summary.get("totals", {})
    st.subheader("Totals")
    t = st.columns(4)
    t[0].metric("Active listings", totals.get("active_listings", 0))
    t[1].metric("Stale listings", totals.get("stale_listings", 0))
    t[2].metric("Total matches", totals.get("total_matches", 0))
    t[3].metric("Un-notified", totals.get("unnotified_matches", 0))

    # ---- pipeline health ----------------------------------------------------------
    st.subheader("Pipeline health (raw_listings)")
    raw = summary.get("raw_health", {})
    h = st.columns(3)
    h[0].metric("Pending", raw.get("pending", 0))
    h[1].metric("Parsed", raw.get("parsed", 0))
    h[2].metric("Error", raw.get("error", 0))

    # ---- portals ------------------------------------------------------------------
    st.subheader("Portals")
    portals = summary.get("portals", [])
    if portals:
        st.dataframe(
            [{"name": p.get("name"),
              "enabled": bool(p.get("enabled")),
              "last_run_at": p.get("last_run_at") or "never"}
             for p in portals],
            use_container_width=True, hide_index=True)
    else:
        st.info("No portals configured.")

    # ---- recent parse errors ------------------------------------------------------
    st.subheader("Recent parse errors")
    errors = summary.get("recent_errors", [])
    if errors:
        st.dataframe(
            [{"url": e.get("url"), "parse_error": e.get("parse_error")}
             for e in errors],
            use_container_width=True, hide_index=True)
    else:
        st.success("No recent parse errors.")

    # ---- run history --------------------------------------------------------------
    st.subheader("Run history")
    runs = db.recent_runs(20)
    if runs:
        st.dataframe(
            [{"started_at": r.get("started_at"),
              "finished_at": r.get("finished_at") or "(running)",
              "raw_fetched": r.get("raw_fetched"),
              "parsed_ok": r.get("parsed_ok"),
              "parse_errors": r.get("parse_errors"),
              "new_matches": r.get("new_matches"),
              "notified": r.get("notified")}
             for r in runs],
            use_container_width=True, hide_index=True)
    else:
        st.info("No runs recorded yet.")


def page_settings():
    st.title("Settings")
    st.caption("Live matcher tuning knobs (D17) — stored in the DB, applied on the next "
               "scheduler run. matcher.py stays pure; these are passed in at runtime.")

    knobs = db.all_settings()
    HELP = {
        "threshold": "Min score (0-1) for a listing to count as a match.",
        "w_size": "Weight on size closeness.",
        "w_price": "Weight on price fit.",
        "w_sector": "Weight on sector match.",
        "budget_softcap_pct": "Fraction over budget_max still scored (e.g. 0.05 = +5%).",
        "sector_miss_fit": "Score (0-1) given to a non-matching sector.",
        "stale_threshold_runs": "Missed 6h runs before a listing is marked stale.",
    }
    with st.form("settings_form"):
        new_vals = {}
        for key in ("threshold", "w_size", "w_price", "w_sector",
                    "budget_softcap_pct", "sector_miss_fit", "stale_threshold_runs"):
            new_vals[key] = st.number_input(
                key, value=float(knobs.get(key, 0.0)), step=0.05,
                help=HELP.get(key, ""))
        w_sum = new_vals["w_size"] + new_vals["w_price"] + new_vals["w_sector"]
        if abs(w_sum - 1.0) > 1e-6:
            st.warning(f"Weights sum to {w_sum:.2f} (not 1.0). Scores can exceed 1; "
                       "that's allowed but the threshold is calibrated for sum=1.0.")
        if st.form_submit_button("Save settings"):
            for key, value in new_vals.items():
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
