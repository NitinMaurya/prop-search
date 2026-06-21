// Types mirroring the FastAPI schemas (apps/api/schemas.py / packages/types/openapi.json).

export type Verdict = "like" | "nope";

export interface Requirement {
  id: number;
  owner?: string | null;
  property_type: string;
  sizes_sqm: number[];
  size_tolerance_pct: number;
  budget_min?: number | null;
  budget_max?: number | null;
  sectors: string[];
  active: boolean;
  created_at?: string | null;
}

export type RequirementInput = Omit<Requirement, "id" | "created_at">;

export interface Match {
  match_id: number;
  requirement_id: number;
  score?: number | null;
  id: number; // listing id
  url?: string | null;
  title?: string | null;
  price?: number | null;
  size_sqm?: number | null;
  sector?: string | null;
  image_url?: string | null;
  advertiser?: string | null;
  ownership?: string | null;
  approving_authority?: string | null;
  description?: string | null;
  is_stale?: boolean | null;
  first_seen_at?: string | null;
  owner?: string | null;
  verdict?: Verdict | null;
  pass_reason?: string | null;
  contacted_at?: string | null;
  notes?: string | null;
  is_new: boolean;
}

export interface Portal {
  id: number;
  name: string;
  enabled: boolean;
  last_run_at?: string | null;
}

export interface Run {
  id: number;
  started_at?: string | null;
  finished_at?: string | null;
  raw_fetched?: number;
  parsed_ok?: number;
  parse_errors?: number;
  new_matches?: number;
  notified?: number;
  error?: string | null;
}

export interface SystemStatus {
  totals: { active: number; stale: number };
  portals: Portal[];
  runs: Run[];
}
