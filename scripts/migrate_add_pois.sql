-- Phase 5.1: real POI storage for Overpass (+ optional Places) ingest.
-- Safe to run on an existing Supabase DB after cities are seeded.

BEGIN;

CREATE TABLE IF NOT EXISTS pois (
  id                    UUID PRIMARY KEY,
  city_id               UUID NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  category              TEXT NOT NULL,
  description           TEXT NOT NULL DEFAULT '',
  latitude              NUMERIC(9, 6),
  longitude             NUMERIC(9, 6),
  price_level           SMALLINT,
  rating                NUMERIC(3, 2),
  safety_score          SMALLINT NOT NULL DEFAULT 3,
  tags                  TEXT[] NOT NULL DEFAULT '{}',
  cost_usd              NUMERIC(10, 2),
  duration_minutes      INTEGER,
  osm_id                BIGINT,
  osm_type              TEXT,
  source                TEXT NOT NULL DEFAULT 'overpass',
  places_primary_type   TEXT,
  user_ratings_total    INTEGER,
  address               TEXT,
  is_active             BOOLEAN NOT NULL DEFAULT TRUE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT pois_category_valid CHECK (category IN ('attraction', 'food', 'rest')),
  CONSTRAINT pois_price_level_range CHECK (
    price_level IS NULL OR price_level BETWEEN 0 AND 4
  ),
  CONSTRAINT pois_rating_range CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
  CONSTRAINT pois_safety_score_range CHECK (safety_score BETWEEN 1 AND 5),
  CONSTRAINT pois_duration_positive CHECK (
    duration_minutes IS NULL OR duration_minutes >= 1
  ),
  CONSTRAINT pois_latitude_range CHECK (
    latitude IS NULL OR latitude BETWEEN -90 AND 90
  ),
  CONSTRAINT pois_longitude_range CHECK (
    longitude IS NULL OR longitude BETWEEN -180 AND 180
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pois_osm_unique
  ON pois (osm_type, osm_id)
  WHERE osm_id IS NOT NULL AND osm_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pois_city_id ON pois (city_id);
CREATE INDEX IF NOT EXISTS idx_pois_category ON pois (category);
CREATE INDEX IF NOT EXISTS idx_pois_city_category ON pois (city_id, category);
CREATE INDEX IF NOT EXISTS idx_pois_active ON pois (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_pois_tags_gin ON pois USING GIN (tags);

DROP TRIGGER IF EXISTS trg_pois_updated_at ON pois;
CREATE TRIGGER trg_pois_updated_at
  BEFORE UPDATE ON pois
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE pois IS 'Real-world POIs ingested from OSM Overpass (+ optional Google Places enrichment).';
COMMENT ON COLUMN pois.price_level IS '0=free … 4=very expensive; from Places or OSM heuristic.';
COMMENT ON COLUMN pois.safety_score IS 'Inherited from city.safety_index unless overridden.';

COMMIT;
