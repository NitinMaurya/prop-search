"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Match, Verdict } from "./types";

type Ctx = { prev: [readonly unknown[], Match[] | undefined][] };

/** Like/Pass(+reason)/Contacted mutations for a match, with optimistic cache updates so
 * the UI responds instantly despite the far DB. Shared by the card and the lightbox. */
export function useMatchActions(m: Match | undefined) {
  const qc = useQueryClient();

  const optimistic = async (changes: Partial<Match>): Promise<Ctx> => {
    await qc.cancelQueries({ queryKey: ["matches"] });
    const prev = qc.getQueriesData<Match[]>({ queryKey: ["matches"] });
    qc.setQueriesData<Match[]>({ queryKey: ["matches"] }, (old) =>
      old?.map((x) => (m && x.id === m.id ? { ...x, ...changes } : x)));
    return { prev };
  };
  const rollback = (_e: unknown, _v: unknown, ctx?: Ctx) =>
    ctx?.prev?.forEach(([k, d]) => qc.setQueryData(k, d));
  const settle = () => qc.invalidateQueries({ queryKey: ["matches"] });

  const feedback = useMutation<void, Error, { v: Verdict; reason?: string }, Ctx>({
    mutationFn: ({ v, reason }) => api.setFeedback(m!.id, v, reason),
    onMutate: ({ v, reason }) =>
      reason != null
        ? optimistic({ verdict: "nope", pass_reason: m?.pass_reason === reason ? null : reason })
        : optimistic({ verdict: m?.verdict === v ? null : v, pass_reason: null }),
    onError: rollback,
    onSettled: settle,
  });
  const contacted = useMutation<{ contacted: boolean }, Error, void, Ctx>({
    mutationFn: () => api.setContacted(m!.id),
    onMutate: () => optimistic({ contacted_at: m?.contacted_at ? null : new Date().toISOString() }),
    onError: rollback,
    onSettled: settle,
  });

  return { feedback, contacted };
}

export const PASS_REASONS: [string, string][] = [
  ["over_budget", "💸 Over budget"],
  ["fake", "🎭 Fake / spam"],
  ["location", "📍 Location"],
  ["condition", "🏚️ Size / condition"],
  ["disliked", "👎 Didn’t like"],
  ["agent", "🚫 Agent"],
];
