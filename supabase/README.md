# Supabase (central store)

Hosted Postgres + Auth. This is the single source of truth; schema lives in `migrations/`.

## One-time setup

1. Create a project at https://supabase.com (region close to the India scraper box, e.g.
   `ap-south-1` Mumbai, keeps writes fast).
2. Apply the schema — either:
   - **SQL editor:** paste `migrations/0001_initial_schema.sql` then `0002_seed.sql`, run; or
   - **CLI:** `supabase link --project-ref <ref>` then `supabase db push`.
3. **Auth:** Authentication → Providers → enable Email (magic link is simplest for 2–3
   users). Add each user under Authentication → Users (or let them sign up).
4. Grab keys from Project Settings → API:
   - `Project URL` and `anon` key → the **web** app (browser-safe).
   - `service_role` key → the **scraper** and **api** only (server-side; never in the browser).
   - Postgres connection string → the **api** (`Project Settings → Database`).

## Keys → where they go

| Key | Used by | In the browser? |
|-----|---------|-----------------|
| `anon` + user JWT | `apps/web` | yes (safe) |
| `service_role` | `apps/scraper`, `apps/api` | **never** |
| Postgres connection string | `apps/api` | no |

## Notes

- RLS is enabled on every table (see `0001`). The browser can only reach the signed-in
  user's own rows; the scraper/api use the service-role key to bypass RLS for writes.
- The scraper writing every 6h keeps a free-tier project from auto-pausing.
