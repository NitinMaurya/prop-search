"""REST routers under /v1. Thin: validate → call db → shape response. Matches filtering
and sorting reuse packages/core (matcher) so the rules match the scraper + the old UI.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from prop_search_core import matcher

from . import db
from .auth import get_user_id
from .schemas import (ContactedIn, FeedbackIn, MatchOut, NoteIn, RequirementIn,
                      RequirementOut)

router = APIRouter(prefix="/v1")


def _row_to_requirement(r: dict) -> dict:
    """created_at -> iso string for JSON."""
    out = dict(r)
    out.pop("user_id", None)
    if out.get("created_at") is not None and not isinstance(out["created_at"], str):
        out["created_at"] = out["created_at"].isoformat()
    return out


# ----------------------------------------------------------------- requirements
@router.get("/requirements", response_model=list[RequirementOut])
def get_requirements(uid: str = Depends(get_user_id)):
    return [_row_to_requirement(r) for r in db.list_requirements(uid)]


@router.post("/requirements", response_model=RequirementOut, status_code=201)
def post_requirement(body: RequirementIn, uid: str = Depends(get_user_id)):
    return _row_to_requirement(db.create_requirement(uid, body.model_dump()))


@router.patch("/requirements/{req_id}", response_model=RequirementOut)
def patch_requirement(req_id: int, body: RequirementIn, uid: str = Depends(get_user_id)):
    row = db.update_requirement(uid, req_id, body.model_dump())
    if row is None:
        raise HTTPException(404, "Requirement not found")
    return _row_to_requirement(row)


@router.delete("/requirements/{req_id}", status_code=204)
def remove_requirement(req_id: int, uid: str = Depends(get_user_id)):
    if not db.delete_requirement(uid, req_id):
        raise HTTPException(404, "Requirement not found")


# ----------------------------------------------------------------- matches
_SHOW = {
    "liked_new": lambda v: v != "nope",
    "liked": lambda v: v == "like",
    "unrated": lambda v: v is None,
    "passed": lambda v: v == "nope",
    "all": lambda v: True,
}
_SORT = {
    "best": lambda m: (m.get("score") is None, -(m.get("score") or 0)),
    "price_asc": lambda m: (m.get("price") is None, m.get("price") or 0),
    "price_desc": lambda m: (m.get("price") is None, -(m.get("price") or 0)),
    "size_asc": lambda m: (m.get("size_sqm") is None, m.get("size_sqm") or 0),
    "size_desc": lambda m: (m.get("size_sqm") is None, -(m.get("size_sqm") or 0)),
}


@router.get("/matches", response_model=list[MatchOut])
def get_matches(
    uid: str = Depends(get_user_id),
    requirement_id: int | None = Query(default=None),
    show: str = Query(default="liked_new"),
    sort: str = Query(default="best"),
    sectors: str = Query(default="", description="comma-separated sector numbers"),
):
    # Single DB round-trip: NOIDA filter + is_new are computed in SQL (see db.list_matches).
    rows = db.list_matches(uid)

    if requirement_id is not None:
        rows = [m for m in rows if m["requirement_id"] == requirement_id]

    keep = _SHOW.get(show, _SHOW["liked_new"])
    rows = [m for m in rows if keep(m.get("verdict"))]

    sector_nums = [s.strip() for s in sectors.split(",") if s.strip()]
    if sector_nums:
        rows = [m for m in rows if matcher._sector_num(m.get("sector")) in sector_nums]

    rows.sort(key=_SORT.get(sort, _SORT["best"]))

    for m in rows:
        for k in ("first_seen_at", "contacted_at"):
            if m.get(k) is not None and not isinstance(m[k], str):
                m[k] = m[k].isoformat()
    return rows


# ----------------------------------------------------------------- feedback / tracking
@router.post("/feedback", status_code=204)
def post_feedback(body: FeedbackIn, uid: str = Depends(get_user_id)):
    db.set_feedback(uid, body.listing_id, body.verdict, body.reason)


@router.post("/tracking/contacted")
def post_contacted(body: ContactedIn, uid: str = Depends(get_user_id)):
    return {"contacted": db.set_contacted(uid, body.listing_id)}


@router.put("/tracking/notes", status_code=204)
def put_notes(body: NoteIn, uid: str = Depends(get_user_id)):
    db.set_note(uid, body.listing_id, body.notes)


# ----------------------------------------------------------------- settings (global)
@router.get("/settings")
def get_settings(uid: str = Depends(get_user_id)):
    return db.get_settings()


@router.put("/settings")
def put_settings(values: dict, uid: str = Depends(get_user_id)):
    return db.update_settings(values)


# ----------------------------------------------------------------- system (global)
@router.get("/system")
def get_system(uid: str = Depends(get_user_id)):
    s = db.system_status()
    for run in s["runs"]:
        for k in ("started_at", "finished_at"):
            if run.get(k) is not None and not isinstance(run[k], str):
                run[k] = run[k].isoformat()
    for p in s["portals"]:
        if p.get("last_run_at") is not None and not isinstance(p["last_run_at"], str):
            p["last_run_at"] = p["last_run_at"].isoformat()
    return s
