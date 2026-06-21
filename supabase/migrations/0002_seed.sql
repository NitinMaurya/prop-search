-- Seed data: portals + default scoring settings (mirrors the MVP seeds).
-- Safe to re-run (on conflict do nothing).

insert into portals (name, base_url, search_url_template, enabled) values
    ('MagicBricks', 'https://www.magicbricks.com',
     'https://www.magicbricks.com/property-for-sale/residential-real-estate?proptype=Residential-House,Villa&cityName=Noida',
     true),
    ('99acres',     'https://www.99acres.com', '', false),
    ('Housing.com', 'https://housing.com',     '', false)
on conflict (name) do nothing;

insert into settings (key, value) values
    ('threshold',            '0.6'),   -- min match score to surface
    ('w_size',               '0.4'),   -- scoring weights (D5/D17)
    ('w_price',              '0.4'),
    ('w_sector',             '0.2'),
    ('size_tolerance_pct',   '30'),    -- D17
    ('noida_authority_only', '1'),     -- D21
    ('stale_threshold',      '3')      -- runs missed before a listing is stale
on conflict (key) do nothing;
