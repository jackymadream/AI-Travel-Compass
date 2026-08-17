-- Optional photo_url for itinerary timeline cards (Phase planner photos).
ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_url TEXT;
