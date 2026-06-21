"""prop_search_core — shared business logic for the v2 scraper + API.

Ported from the v1 MVP (matcher, property types, notifier, scrapers). The data-access
layer is intentionally NOT here: in v2 the scraper and API talk to Supabase directly.
"""
