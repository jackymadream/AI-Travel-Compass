-- Apply on existing Supabase DB if cities.tags is missing
-- Run once in Supabase SQL Editor before re-seeding.

ALTER TABLE cities
  ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_cities_tags_gin ON cities USING GIN (tags);

COMMENT ON COLUMN cities.tags IS
  'Soft preference tags for ranking/RAG, e.g. culture, nature, budget-friendly.';
