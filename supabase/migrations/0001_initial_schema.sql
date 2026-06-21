-- prop-search v2 — initial schema
-- Ported from the MVP SQLite schema (db.py) with multi-user ownership + Row-Level
-- Security. See docs/V2_PLAN.md §5.
--
-- Apply: Supabase SQL editor (paste & run) OR `supabase db push` with the CLI.

-- ============================================================ global (scraper-produced)
-- These are written by the scraper node using the service-role key (bypasses RLS) and
-- are read-only to authenticated users.

create table portals (
    id                  bigint generated always as identity primary key,
    name                text not null unique,
    base_url            text not null,
    search_url_template text not null,
    enabled             boolean not null default false,
    last_run_at         timestamptz
);

create table listings (
    id                  bigint generated always as identity primary key,
    portal_id           bigint not null references portals(id),
    external_id         text,
    url                 text,
    title               text,
    price               bigint,
    size_sqm            double precision,
    sector              text,
    raw_location        text,
    posted_date         text,
    image_url           text,
    advertiser          text,
    ownership           text,
    approving_authority text,
    description         text,
    fingerprint         text not null unique,          -- dedup key (D7)
    first_seen_at       timestamptz not null default now(),
    last_seen_at        timestamptz not null default now(),
    is_stale            boolean not null default false
);
create index listings_sector_idx on listings (sector);
create index listings_stale_idx  on listings (is_stale);

create table runs (
    id           bigint generated always as identity primary key,
    started_at   timestamptz not null default now(),
    finished_at  timestamptz,
    raw_fetched  integer default 0,
    parsed_ok    integer default 0,
    parse_errors integer default 0,
    new_matches  integer default 0,
    notified     integer default 0
);

create table settings (
    key   text primary key,
    value text not null
);

-- ============================================================ per-user
-- Owned rows. Users only ever see their own via RLS.

create table requirements (
    id                 bigint generated always as identity primary key,
    user_id            uuid not null references auth.users(id) on delete cascade,
    owner              text,                       -- optional display label
    property_type      text not null default 'house',
    sizes_sqm          jsonb not null default '[]',
    size_tolerance_pct double precision not null default 30,
    budget_min         bigint,
    budget_max         bigint,
    sectors            jsonb not null default '[]',
    active             boolean not null default true,
    created_at         timestamptz not null default now()
);
create index requirements_user_idx on requirements (user_id);

create table matches (
    id             bigint generated always as identity primary key,
    requirement_id bigint not null references requirements(id) on delete cascade,
    listing_id     bigint not null references listings(id) on delete cascade,
    score          double precision,
    notified       boolean not null default false,
    created_at     timestamptz not null default now(),
    unique (requirement_id, listing_id)
);
create index matches_requirement_idx on matches (requirement_id);
create index matches_listing_idx     on matches (listing_id);

create table feedback (
    user_id    uuid   not null references auth.users(id) on delete cascade,
    listing_id bigint not null references listings(id)   on delete cascade,
    verdict    text   not null check (verdict in ('like', 'nope')),
    reason     text,                                -- pass reason (D29), nullable
    updated_at timestamptz not null default now(),
    primary key (user_id, listing_id)
);

create table tracking (
    user_id      uuid   not null references auth.users(id) on delete cascade,
    listing_id   bigint not null references listings(id)   on delete cascade,
    contacted_at timestamptz,                        -- null = not contacted
    notes        text,
    updated_at   timestamptz not null default now(),
    primary key (user_id, listing_id)
);

-- ============================================================ Row-Level Security
alter table portals      enable row level security;
alter table listings     enable row level security;
alter table runs         enable row level security;
alter table settings     enable row level security;
alter table requirements enable row level security;
alter table matches      enable row level security;
alter table feedback     enable row level security;
alter table tracking     enable row level security;

-- Global tables: any authenticated user may read. Writes happen only via the service-role
-- key (scraper / API), which bypasses RLS — so no write policies are needed.
create policy "read portals"  on portals  for select to authenticated using (true);
create policy "read listings" on listings for select to authenticated using (true);
create policy "read runs"     on runs     for select to authenticated using (true);
create policy "read settings" on settings for select to authenticated using (true);

-- requirements: owner has full access to their own rows.
create policy "own requirements" on requirements for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- matches: readable when the parent requirement belongs to the user.
create policy "own matches" on matches for select to authenticated
    using (exists (
        select 1 from requirements r
        where r.id = matches.requirement_id and r.user_id = auth.uid()));

-- feedback / tracking: owner-only.
create policy "own feedback" on feedback for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own tracking" on tracking for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());
