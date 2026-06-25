"use client";

import { accessToken } from "./supabase";
import type {
  Match, Requirement, RequirementInput, SystemStatus, Verdict,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface MatchFilters {
  requirement_id?: number;
  show?: string;
  sort?: string;
  sectors?: string;
}

export const api = {
  // requirements
  listRequirements: () => request<Requirement[]>("/requirements"),
  createRequirement: (r: RequirementInput) =>
    request<Requirement>("/requirements", { method: "POST", body: JSON.stringify(r) }),
  updateRequirement: (id: number, r: RequirementInput) =>
    request<Requirement>(`/requirements/${id}`, { method: "PATCH", body: JSON.stringify(r) }),
  deleteRequirement: (id: number) =>
    request<void>(`/requirements/${id}`, { method: "DELETE" }),

  // matches
  listMatches: (f: MatchFilters = {}) => {
    const q = new URLSearchParams();
    if (f.requirement_id != null) q.set("requirement_id", String(f.requirement_id));
    if (f.show) q.set("show", f.show);
    if (f.sort) q.set("sort", f.sort);
    if (f.sectors) q.set("sectors", f.sectors);
    const qs = q.toString();
    return request<Match[]>(`/matches${qs ? `?${qs}` : ""}`);
  },

  // feedback / tracking
  setFeedback: (listing_id: number, verdict: Verdict, reason?: string | null) =>
    request<void>("/feedback", {
      method: "POST",
      body: JSON.stringify({ listing_id, verdict, reason: reason ?? null }),
    }),
  setContacted: (listing_id: number, contacted?: boolean) =>
    request<{ contacted: boolean }>("/tracking/contacted", {
      method: "POST", body: JSON.stringify({ listing_id, contacted: contacted ?? null }),
    }),
  setNote: (listing_id: number, notes: string) =>
    request<void>("/tracking/notes", {
      method: "PUT", body: JSON.stringify({ listing_id, notes }),
    }),

  // settings / system
  getSettings: () => request<Record<string, string>>("/settings"),
  updateSettings: (values: Record<string, string | number>) =>
    request<Record<string, string>>("/settings", {
      method: "PUT", body: JSON.stringify(values),
    }),
  getSystem: () => request<SystemStatus>("/system"),
};
