-- GenAI Travel Compass — PostgreSQL schema
-- Requires PostgreSQL 14+

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- Shared types
-- ---------------------------------------------------------------------------

CREATE TYPE locale_code AS ENUM ('en', 'zh-HK', 'ja');

CREATE TYPE travel_season AS ENUM ('spring', 'summer', 'autumn', 'winter');

-- I18n JSONB contract (en / zh-HK / ja):
--   {"en": "Tokyo", "zh-HK": "東京", "ja": "東京"}
-- Access: column->'zh-HK' or i18n_text_at(column, 'zh-HK'::locale_code)
CREATE OR REPLACE FUNCTION is_valid_i18n_text(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    jsonb_typeof(value) = 'object'
    AND value ? 'en'
    AND value ? 'zh-HK'
    AND value ? 'ja'
    AND (value->>'en') <> ''
    AND (value->>'zh-HK') <> ''
    AND (value->>'ja') <> '';
$$;

CREATE OR REPLACE FUNCTION i18n_text_at(value JSONB, locale locale_code)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT value ->> locale::TEXT;
$$;

-- Best travel season payload:
-- {"seasons": ["spring", "autumn"], "months": [3, 4, 5, 9, 10, 11],
--  "label": {"en": "...", "zh-HK": "...", "ja": "..."}}
CREATE OR REPLACE FUNCTION is_valid_best_travel_season(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    jsonb_typeof(value) = 'object'
    AND jsonb_typeof(value->'seasons') = 'array'
    AND jsonb_typeof(value->'months') = 'array'
    AND is_valid_i18n_text(value->'label')
    AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(value->'seasons') AS season(value)
      WHERE season.value NOT IN ('spring', 'summer', 'autumn', 'winter')
    )
    AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements(value->'months') AS month(value)
      WHERE (month.value)::INT < 1 OR (month.value)::INT > 12
    );
$$;

CREATE OR REPLACE FUNCTION is_valid_month_array(months SMALLINT[])
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT COALESCE(
    bool_and(month_value BETWEEN 1 AND 12),
    TRUE
  )
  FROM unnest(months) AS month(month_value);
$$;

-- ---------------------------------------------------------------------------
-- countries
-- ---------------------------------------------------------------------------

CREATE TABLE countries (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  iso_code            CHAR(2) NOT NULL,
  name                JSONB NOT NULL,
  description         JSONB NOT NULL,
  safety_index        SMALLINT NOT NULL,
  avg_daily_cost_usd  NUMERIC(10, 2) NOT NULL,
  best_travel_season  JSONB NOT NULL,
  region_tags         TEXT[] NOT NULL DEFAULT '{}',
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT countries_iso_code_unique UNIQUE (iso_code),
  CONSTRAINT countries_safety_index_range CHECK (safety_index BETWEEN 1 AND 5),
  CONSTRAINT countries_avg_daily_cost_positive CHECK (avg_daily_cost_usd > 0),
  CONSTRAINT countries_name_i18n CHECK (is_valid_i18n_text(name)),
  CONSTRAINT countries_description_i18n CHECK (is_valid_i18n_text(description)),
  CONSTRAINT countries_best_travel_season_valid CHECK (is_valid_best_travel_season(best_travel_season))
);

COMMENT ON TABLE countries IS 'Destination countries with multilingual metadata and travel signals.';
COMMENT ON COLUMN countries.name IS 'Localized display name: en / zh-HK / ja.';
COMMENT ON COLUMN countries.description IS 'Localized introduction for recommendation cards and GenAI context.';
COMMENT ON COLUMN countries.safety_index IS 'Subjective safety score from 1 (low) to 5 (high).';
COMMENT ON COLUMN countries.avg_daily_cost_usd IS 'Estimated average daily spend per traveler in USD.';
COMMENT ON COLUMN countries.best_travel_season IS 'Structured season guidance with seasons, months, and localized label.';
COMMENT ON COLUMN countries.region_tags IS 'Region labels for hard exclusion filters, e.g. {East Asia, Middle East}.';

-- ---------------------------------------------------------------------------
-- cities
-- ---------------------------------------------------------------------------

CREATE TABLE cities (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  country_id          UUID NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
  slug                TEXT NOT NULL,
  name                JSONB NOT NULL,
  description         JSONB NOT NULL,
  safety_index        SMALLINT NOT NULL,
  avg_daily_cost_usd  NUMERIC(10, 2) NOT NULL,
  best_travel_season  JSONB NOT NULL,
  latitude            NUMERIC(9, 6),
  longitude           NUMERIC(9, 6),
  tags                TEXT[] NOT NULL DEFAULT '{}',
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT cities_country_slug_unique UNIQUE (country_id, slug),
  CONSTRAINT cities_safety_index_range CHECK (safety_index BETWEEN 1 AND 5),
  CONSTRAINT cities_avg_daily_cost_positive CHECK (avg_daily_cost_usd > 0),
  CONSTRAINT cities_name_i18n CHECK (is_valid_i18n_text(name)),
  CONSTRAINT cities_description_i18n CHECK (is_valid_i18n_text(description)),
  CONSTRAINT cities_best_travel_season_valid CHECK (is_valid_best_travel_season(best_travel_season)),
  CONSTRAINT cities_latitude_range CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  CONSTRAINT cities_longitude_range CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

COMMENT ON TABLE cities IS 'Cities within a country; inherits country context but may override local signals.';
COMMENT ON COLUMN cities.slug IS 'URL-safe identifier unique within the parent country.';
COMMENT ON COLUMN cities.latitude IS 'Optional centroid for map rendering and proximity ranking.';
COMMENT ON COLUMN cities.longitude IS 'Optional centroid for map rendering and proximity ranking.';
COMMENT ON COLUMN cities.tags IS 'Soft preference tags for ranking/RAG, e.g. culture, nature, budget-friendly.';

-- ---------------------------------------------------------------------------
-- pois (Phase 5.1 — Overpass / Places ingest)
-- ---------------------------------------------------------------------------

CREATE TABLE pois (
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

COMMENT ON TABLE pois IS 'Real-world POIs ingested from OSM Overpass (+ optional Google Places enrichment).';
COMMENT ON COLUMN pois.price_level IS '0=free … 4=very expensive; from Places or OSM heuristic.';
COMMENT ON COLUMN pois.safety_score IS 'Inherited from city.safety_index unless overridden.';

-- ---------------------------------------------------------------------------
-- user_itineraries (Phase 5.3 — Supabase Auth persistence)
-- ---------------------------------------------------------------------------

CREATE TABLE user_itineraries (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,
  title             TEXT NOT NULL,
  destination       TEXT NOT NULL,
  city_id           UUID REFERENCES cities(id) ON DELETE SET NULL,
  days_data         JSONB NOT NULL DEFAULT '[]'::JSONB,
  total_cost_usd    NUMERIC(12, 2),
  agent_reasoning   TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT user_itineraries_title_nonempty CHECK (char_length(trim(title)) > 0),
  CONSTRAINT user_itineraries_destination_nonempty CHECK (char_length(trim(destination)) > 0),
  CONSTRAINT user_itineraries_days_data_object_or_array CHECK (
    jsonb_typeof(days_data) IN ('array', 'object')
  )
);

COMMENT ON TABLE user_itineraries IS 'Persisted itineraries owned by Supabase Auth users.';
COMMENT ON COLUMN user_itineraries.user_id IS 'auth.users.id (Supabase Auth subject).';
COMMENT ON COLUMN user_itineraries.days_data IS 'JSON daily plans (DailyItinerary[] or wrapped object).';

-- ---------------------------------------------------------------------------
-- user_profiles
-- ---------------------------------------------------------------------------

CREATE TABLE user_profiles (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL,
  display_name            TEXT,
  preferred_locale        locale_code NOT NULL DEFAULT 'en',
  budget_min_usd          NUMERIC(10, 2),
  budget_max_usd          NUMERIC(10, 2),
  min_safety_index        SMALLINT NOT NULL DEFAULT 3,
  preferred_seasons       travel_season[] NOT NULL DEFAULT '{}',
  preferred_months        SMALLINT[] NOT NULL DEFAULT '{}',
  preferred_country_ids   UUID[] NOT NULL DEFAULT '{}',
  preferred_city_ids      UUID[] NOT NULL DEFAULT '{}',
  excluded_country_ids    UUID[] NOT NULL DEFAULT '{}',
  excluded_city_ids       UUID[] NOT NULL DEFAULT '{}',
  interests               JSONB NOT NULL DEFAULT '[]'::JSONB,
  travel_styles           TEXT[] NOT NULL DEFAULT '{}',
  dietary_preferences     TEXT[] NOT NULL DEFAULT '{}',
  accessibility_needs     TEXT[] NOT NULL DEFAULT '{}',
  party_size              SMALLINT NOT NULL DEFAULT 1,
  typical_trip_days       SMALLINT,
  personalization_notes   TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT user_profiles_user_id_unique UNIQUE (user_id),
  CONSTRAINT user_profiles_min_safety_index_range CHECK (min_safety_index BETWEEN 1 AND 5),
  CONSTRAINT user_profiles_budget_range CHECK (
    budget_min_usd IS NULL
    OR budget_max_usd IS NULL
    OR budget_min_usd <= budget_max_usd
  ),
  CONSTRAINT user_profiles_budget_min_positive CHECK (budget_min_usd IS NULL OR budget_min_usd >= 0),
  CONSTRAINT user_profiles_budget_max_positive CHECK (budget_max_usd IS NULL OR budget_max_usd > 0),
  CONSTRAINT user_profiles_party_size_positive CHECK (party_size >= 1),
  CONSTRAINT user_profiles_typical_trip_days_positive CHECK (typical_trip_days IS NULL OR typical_trip_days >= 1),
  CONSTRAINT user_profiles_preferred_months_valid CHECK (is_valid_month_array(preferred_months)),
  CONSTRAINT user_profiles_interests_is_array CHECK (jsonb_typeof(interests) = 'array')
);

COMMENT ON TABLE user_profiles IS 'End-user travel preferences consumed by ranking and GenAI recommendation flows.';
COMMENT ON COLUMN user_profiles.user_id IS 'External auth subject ID (e.g. Supabase/Firebase UUID).';
COMMENT ON COLUMN user_profiles.interests IS 'Free-form interest tags, e.g. ["food", "hiking", "museums"].';
COMMENT ON COLUMN user_profiles.excluded_country_ids IS 'Hard exclusion list; cities under these countries are removed from the candidate set.';
COMMENT ON COLUMN user_profiles.excluded_city_ids IS 'Hard exclusion list; matching cities are removed from the candidate set.';
COMMENT ON COLUMN user_profiles.personalization_notes IS 'Optional natural-language hints appended to GenAI prompts.';

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_countries_updated_at
  BEFORE UPDATE ON countries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_cities_updated_at
  BEFORE UPDATE ON cities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_pois_updated_at
  BEFORE UPDATE ON pois
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_itineraries_updated_at
  BEFORE UPDATE ON user_itineraries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Indexes — countries
-- ---------------------------------------------------------------------------

CREATE INDEX idx_countries_active ON countries (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_countries_safety_index ON countries (safety_index);
CREATE INDEX idx_countries_avg_daily_cost_usd ON countries (avg_daily_cost_usd);
CREATE INDEX idx_countries_safety_cost ON countries (safety_index, avg_daily_cost_usd);
CREATE INDEX idx_countries_region_tags_gin ON countries USING GIN (region_tags);
CREATE INDEX idx_countries_name_en ON countries ((name->>'en'));
CREATE INDEX idx_countries_name_zh_hk ON countries ((name->>'zh-HK'));
CREATE INDEX idx_countries_name_ja ON countries ((name->>'ja'));
CREATE INDEX idx_countries_name_gin ON countries USING GIN (name jsonb_path_ops);
CREATE INDEX idx_countries_description_gin ON countries USING GIN (description jsonb_path_ops);
CREATE INDEX idx_countries_best_travel_seasons_gin ON countries USING GIN ((best_travel_season->'seasons'));
CREATE INDEX idx_countries_best_travel_months_gin ON countries USING GIN ((best_travel_season->'months'));

-- ---------------------------------------------------------------------------
-- Indexes — cities
-- ---------------------------------------------------------------------------

CREATE INDEX idx_cities_country_id ON cities (country_id);
CREATE INDEX idx_cities_active ON cities (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_cities_safety_index ON cities (safety_index);
CREATE INDEX idx_cities_avg_daily_cost_usd ON cities (avg_daily_cost_usd);
CREATE INDEX idx_cities_safety_cost ON cities (safety_index, avg_daily_cost_usd);
CREATE INDEX idx_cities_name_en ON cities ((name->>'en'));
CREATE INDEX idx_cities_name_zh_hk ON cities ((name->>'zh-HK'));
CREATE INDEX idx_cities_name_ja ON cities ((name->>'ja'));
CREATE INDEX idx_cities_name_gin ON cities USING GIN (name jsonb_path_ops);
CREATE INDEX idx_cities_description_gin ON cities USING GIN (description jsonb_path_ops);
CREATE INDEX idx_cities_best_travel_seasons_gin ON cities USING GIN ((best_travel_season->'seasons'));
CREATE INDEX idx_cities_best_travel_months_gin ON cities USING GIN ((best_travel_season->'months'));
CREATE INDEX idx_cities_country_cost_safety ON cities (country_id, avg_daily_cost_usd, safety_index);
CREATE INDEX idx_cities_tags_gin ON cities USING GIN (tags);

-- ---------------------------------------------------------------------------
-- Indexes — pois
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX idx_pois_osm_unique
  ON pois (osm_type, osm_id)
  WHERE osm_id IS NOT NULL AND osm_type IS NOT NULL;
CREATE INDEX idx_pois_city_id ON pois (city_id);
CREATE INDEX idx_pois_category ON pois (category);
CREATE INDEX idx_pois_city_category ON pois (city_id, category);
CREATE INDEX idx_pois_active ON pois (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_pois_tags_gin ON pois USING GIN (tags);

-- ---------------------------------------------------------------------------
-- Indexes — user_itineraries
-- ---------------------------------------------------------------------------

CREATE INDEX idx_user_itineraries_user_id ON user_itineraries (user_id);
CREATE INDEX idx_user_itineraries_user_created ON user_itineraries (user_id, created_at DESC);
CREATE INDEX idx_user_itineraries_city_id ON user_itineraries (city_id);

-- ---------------------------------------------------------------------------
-- Indexes — user_profiles
-- ---------------------------------------------------------------------------

CREATE INDEX idx_user_profiles_preferred_locale ON user_profiles (preferred_locale);
CREATE INDEX idx_user_profiles_min_safety_index ON user_profiles (min_safety_index);
CREATE INDEX idx_user_profiles_budget_range ON user_profiles (budget_min_usd, budget_max_usd);
CREATE INDEX idx_user_profiles_preferred_seasons_gin ON user_profiles USING GIN (preferred_seasons);
CREATE INDEX idx_user_profiles_preferred_months_gin ON user_profiles USING GIN (preferred_months);
CREATE INDEX idx_user_profiles_preferred_country_ids_gin ON user_profiles USING GIN (preferred_country_ids);
CREATE INDEX idx_user_profiles_preferred_city_ids_gin ON user_profiles USING GIN (preferred_city_ids);
CREATE INDEX idx_user_profiles_excluded_country_ids_gin ON user_profiles USING GIN (excluded_country_ids);
CREATE INDEX idx_user_profiles_excluded_city_ids_gin ON user_profiles USING GIN (excluded_city_ids);
CREATE INDEX idx_user_profiles_interests_gin ON user_profiles USING GIN (interests jsonb_path_ops);
CREATE INDEX idx_user_profiles_travel_styles_gin ON user_profiles USING GIN (travel_styles);

COMMIT;
