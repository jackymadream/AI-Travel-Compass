-- Lock down public.pois for PostgREST without changing FastAPI / ingest.
--
-- FastAPI and seed scripts use SUPABASE_SERVICE_ROLE_KEY, which bypasses RLS.
-- The browser uses the anon key and must not write the POI catalog.
--
-- Safe to re-run.

BEGIN;

ALTER TABLE public.pois ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.pois FROM anon, authenticated;
GRANT SELECT ON TABLE public.pois TO anon, authenticated;

DROP POLICY IF EXISTS pois_select_active ON public.pois;
CREATE POLICY pois_select_active
  ON public.pois
  FOR SELECT
  TO anon, authenticated
  USING (is_active = TRUE);

-- No INSERT/UPDATE/DELETE policies for anon or authenticated.
-- Writes stay with service_role (ingest, photo patch, FastAPI).

COMMIT;
