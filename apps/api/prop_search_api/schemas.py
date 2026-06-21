"""Request/response models. Keep outputs typed so the generated TS client is precise."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------- requirements
class RequirementIn(BaseModel):
    owner: Optional[str] = None
    property_type: str = "house"
    sizes_sqm: list[int] = Field(default_factory=list)
    size_tolerance_pct: float = 30
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    sectors: list[str] = Field(default_factory=list)
    active: bool = True


class RequirementOut(RequirementIn):
    id: int
    created_at: Optional[str] = None


# ----------------------------------------------------------------- matches
class MatchOut(BaseModel):
    match_id: int
    requirement_id: int
    score: Optional[float] = None
    # listing fields (flattened)
    id: int
    url: Optional[str] = None
    title: Optional[str] = None
    price: Optional[int] = None
    size_sqm: Optional[float] = None
    sector: Optional[str] = None
    image_url: Optional[str] = None
    advertiser: Optional[str] = None
    ownership: Optional[str] = None
    approving_authority: Optional[str] = None
    description: Optional[str] = None
    is_stale: Optional[bool] = None
    first_seen_at: Optional[str] = None
    owner: Optional[str] = None
    # the user's per-listing state
    verdict: Optional[Literal["like", "nope"]] = None
    pass_reason: Optional[str] = None
    contacted_at: Optional[str] = None
    notes: Optional[str] = None
    is_new: bool = False


# ----------------------------------------------------------------- feedback / tracking
class FeedbackIn(BaseModel):
    listing_id: int
    verdict: Literal["like", "nope"]
    reason: Optional[str] = None


class ContactedIn(BaseModel):
    listing_id: int


class NoteIn(BaseModel):
    listing_id: int
    notes: str = ""
