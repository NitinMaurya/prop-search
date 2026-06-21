# apps/web (Phase 3)

Next.js (App Router) + shadcn/ui + Tailwind. The UI, reachable from anywhere (Vercel).
Supabase Auth for login; data via TanStack Query against `apps/api` (user JWT in the
Authorization header). Uses only the Supabase **anon** key — never the service-role key.

Screens (ported from the MVP, keeping its UX decisions): Matches (cards/table, lightbox,
like/pass + reasons, contacted, NEW tag, Maps links, sector filter + group, sort),
Shortlist (Liked / Passed / Follow-ups), Requirements (CRUD), System, Settings.

Config: see `.env.example`. Build details land in Phase 3 — see `docs/V2_PLAN.md` §6.
