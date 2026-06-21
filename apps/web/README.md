# apps/web (Phase 3 ✅ built)

Next.js (App Router, TS) + Tailwind v4. The UI, reachable from anywhere (Vercel).
Supabase Auth (email/password) for login; data via TanStack Query against `apps/api`
(user JWT in the Authorization header). Uses only the Supabase **anon** key.

## Layout
- `src/lib/` — `supabase.ts` (browser client), `api.ts` (typed client over the FastAPI),
  `types.ts`, `useSession.ts`, `format.ts`.
- `src/app/login` — sign-in. `src/app/(app)/*` — authed area (guard + sidebar).
- Screens: `matches`, `shortlist`, `requirements`, `system`, `settings`.
- `src/components/` — `Sidebar`, `MatchCard`, `PageHeader`.

## Screens
- **Matches** — Show/Sort/Sector filters, group-by-sector, card grid, like/pass +
  contacted, NEW tag, Maps links.
- **Shortlist** — Liked / Passed / Follow-ups (notes editor + contacted toggle).
- **Requirements** — table + create/edit/delete modal.
- **System** — stat tiles, portals, run history.
- **Settings** — scoring knobs (threshold, weights, tolerance, NOIDA, stale).

## Setup & run
```bash
pnpm install
cp .env.example .env.local      # NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY / _API_BASE_URL
pnpm dev                        # http://localhost:3000
```

Notes: styled with hand-rolled Tailwind primitives matching the v1 aesthetic (shadcn/ui
can be layered on later via its CLI). Listing images use plain `<img>` (hot-linked).
Hosting: Vercel. `pnpm build` typechecks + compiles. See `docs/V2_PLAN.md` §6.
