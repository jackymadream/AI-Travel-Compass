-- Phase 5.3: saved itineraries for authenticated users.

BEGIN;

CREATE TABLE IF NOT EXISTS user_itineraries (
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

CREATE INDEX IF NOT EXISTS idx_user_itineraries_user_id ON user_itineraries (user_id);
CREATE INDEX IF NOT EXISTS idx_user_itineraries_user_created
  ON user_itineraries (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_itineraries_city_id ON user_itineraries (city_id);

DROP TRIGGER IF EXISTS trg_user_itineraries_updated_at ON user_itineraries;
CREATE TRIGGER trg_user_itineraries_updated_at
  BEFORE UPDATE ON user_itineraries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE user_itineraries IS 'Persisted itineraries owned by Supabase Auth users.';
COMMENT ON COLUMN user_itineraries.user_id IS 'auth.users.id (Supabase Auth subject).';
COMMENT ON COLUMN user_itineraries.days_data IS 'JSON daily plans (DailyItinerary[] or wrapped object).';

-- Optional RLS (enable when using anon key from client; backend uses service role).
ALTER TABLE user_itineraries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_itineraries_select_own ON user_itineraries;
CREATE POLICY user_itineraries_select_own ON user_itineraries
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS user_itineraries_insert_own ON user_itineraries;
CREATE POLICY user_itineraries_insert_own ON user_itineraries
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS user_itineraries_update_own ON user_itineraries;
CREATE POLICY user_itineraries_update_own ON user_itineraries
  FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS user_itineraries_delete_own ON user_itineraries;
CREATE POLICY user_itineraries_delete_own ON user_itineraries
  FOR DELETE USING (auth.uid() = user_id);

COMMIT;
