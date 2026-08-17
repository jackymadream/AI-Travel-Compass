-- Phase 6.1: extend countries for browse cards (slug, photo, tags, top_cities).
-- Apply in Supabase SQL Editor before running scripts/seed_countries.py.

ALTER TABLE countries
  ADD COLUMN IF NOT EXISTS slug TEXT,
  ADD COLUMN IF NOT EXISTS photo_url TEXT,
  ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS top_cities JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Backfill slug from lowercase English name when missing (seed will overwrite).
UPDATE countries
SET slug = lower(regexp_replace(COALESCE(name->>'en', iso_code), '[^a-zA-Z0-9]+', '-', 'g'))
WHERE slug IS NULL OR btrim(slug) = '';

-- Unique slug (partial nulls allowed until fully seeded).
CREATE UNIQUE INDEX IF NOT EXISTS idx_countries_slug ON countries (slug)
  WHERE slug IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_countries_tags_gin ON countries USING GIN (tags);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'countries_top_cities_is_array'
  ) THEN
    ALTER TABLE countries
      ADD CONSTRAINT countries_top_cities_is_array
      CHECK (jsonb_typeof(top_cities) = 'array');
  END IF;
END $$;

COMMENT ON COLUMN countries.slug IS 'Stable text id for browse UI (e.g. japan); UUID id remains the PK.';
COMMENT ON COLUMN countries.tags IS 'Theme tags for soft browse filters (culture, nature, food, beach, etc.).';
COMMENT ON COLUMN countries.photo_url IS 'Representative landscape/architecture image URL (Unsplash).';
COMMENT ON COLUMN countries.top_cities IS 'JSONB snapshot of 2–4 representative cities for country cards.';
COMMENT ON COLUMN countries.description IS 'Localized introduction for recommendation cards and GenAI context (Phase 6.1 summary).';
