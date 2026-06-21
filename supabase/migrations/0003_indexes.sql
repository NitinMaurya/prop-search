-- Indexing pass, tuned to the real query patterns (v2).
--
-- Already covered by 0001 / constraints:
--   requirements(user_id)                      → list + RLS
--   matches UNIQUE(requirement_id, listing_id) → the matches join from a requirement
--   matches(listing_id)                        → joins from the listing side
--   listings UNIQUE(fingerprint)               → scraper upsert dedup
--   feedback/tracking PK(user_id, listing_id)  → the per-user LEFT JOINs in /matches
--
-- This migration adds what those don't, and drops a redundant index.

-- runs: the is_new subquery (max(started_at)) + the System run-history ordering.
create index if not exists runs_started_at_idx on runs (started_at desc);

-- listings staleness: mark_stale() sweeps `is_stale = false AND last_seen_at < cutoff`,
-- and active-listings reads filter `is_stale = false`. A partial index on the fresh rows
-- serves both without indexing the (rare) stale rows.
create index if not exists listings_fresh_lastseen_idx
    on listings (last_seen_at) where is_stale = false;

-- matches.requirement_id is the leading column of the UNIQUE(requirement_id, listing_id)
-- index, so the standalone index from 0001 is redundant — drop it to save write cost.
drop index if exists matches_requirement_idx;
