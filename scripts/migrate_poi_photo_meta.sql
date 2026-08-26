-- Photo provenance for ingest-time POI images (planner copies photo_url; no live Wikipedia).
BEGIN;

ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_url TEXT;
ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_source TEXT;
ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_confidence TEXT;
ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_checked_at TIMESTAMPTZ;
ALTER TABLE pois ADD COLUMN IF NOT EXISTS google_place_name TEXT;
ALTER TABLE pois ADD COLUMN IF NOT EXISTS google_photo_name TEXT;

ALTER TABLE pois DROP CONSTRAINT IF EXISTS pois_photo_source_valid;
ALTER TABLE pois ADD CONSTRAINT pois_photo_source_valid CHECK (
  photo_source IS NULL OR photo_source IN (
    'wikidata', 'wikipedia', 'places', 'cuisine_seed', 'none'
  )
);

ALTER TABLE pois DROP CONSTRAINT IF EXISTS pois_photo_confidence_valid;
ALTER TABLE pois ADD CONSTRAINT pois_photo_confidence_valid CHECK (
  photo_confidence IS NULL OR photo_confidence IN ('high', 'medium', 'low')
);

COMMENT ON COLUMN pois.photo_url IS 'Grounded image resolved at ingest (Wikidata/Wikipedia/Places) or cuisine seed; null if none.';
COMMENT ON COLUMN pois.photo_source IS 'wikidata | wikipedia | places | cuisine_seed | none';
COMMENT ON COLUMN pois.photo_confidence IS 'high | medium | low';
COMMENT ON COLUMN pois.photo_checked_at IS 'When photo enricher last ran for this row.';
COMMENT ON COLUMN pois.google_place_name IS 'Google Places resource name used for photo fallback reuse, e.g. places/ChIJ...';
COMMENT ON COLUMN pois.google_photo_name IS 'Google Places photo resource name used to refresh a stored photo without another search.';

COMMIT;
