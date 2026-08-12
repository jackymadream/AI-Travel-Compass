export type Locale = "en" | "zh-HK" | "ja";

export type BestTravelSeason = {
  seasons: string[];
  months: number[];
  label: string;
};

export type Country = {
  id: string;
  iso_code: string;
  name: string;
  description: string;
  safety_index: number;
  avg_daily_cost_usd: number;
  best_travel_season: BestTravelSeason;
  region_tags: string[];
};

export type CountryFilters = {
  locale: Locale;
  maxBudget: number;
  minSafety: number;
};

export type SearchRequest = {
  query: string;
  locale: Locale;
  max_budget?: number;
  min_safety?: number;
  tags?: string[];
  limit?: number;
};

export type SearchHit = {
  city_id: string | null;
  country_id: string | null;
  iso_code: string | null;
  name: string;
  description: string;
  safety_index: number;
  avg_daily_cost_usd: number;
  tags: string[];
  score: number;
  vector_score: number | null;
};

export type SearchResponse = {
  query: string;
  locale: Locale;
  candidate_count: number;
  empty_reason: string | null;
  results: SearchHit[];
};

export type TripPace = "relaxed" | "moderate" | "packed";
export type ActivityCategory = "attraction" | "food" | "rest";

export type ItineraryRequest = {
  city_id: string;
  days: number;
  pace: TripPace;
  daily_budget_usd: number;
  preferences?: string[];
  locale?: Locale;
};

export type Activity = {
  time_slot: string;
  poi_name: string;
  category: ActivityCategory;
  cost_usd: number;
  duration_minutes: number;
  description: string;
};

export type DailyItinerary = {
  day_number: number;
  theme: string;
  estimated_daily_cost: number;
  activities: Activity[];
};

export type ItineraryResponse = {
  city_name: string;
  total_cost_usd: number;
  daily_plans: DailyItinerary[];
  agent_reasoning: string;
};

/** Fallback cities if GET /cities is unavailable (mock POI IDs). */
export const PLANNER_CITIES = [
  {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    name: "Tokyo (mock)",
  },
  {
    id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    name: "Seoul (mock)",
  },
] as const;

export type CitySummary = {
  id: string;
  slug: string;
  name: string;
  country_iso?: string | null;
  safety_index?: number | null;
  avg_daily_cost_usd?: number | null;
  tags?: string[];
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || DEFAULT_API_BASE
  );
}

export async function fetchCities(
  locale: Locale = "en",
  signal?: AbortSignal
): Promise<CitySummary[]> {
  const params = new URLSearchParams({ locale, limit: "50" });
  const res = await fetch(`${getApiBaseUrl()}/api/v1/cities?${params}`, {
    signal,
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to load cities (${res.status})`);
  }
  return (await res.json()) as CitySummary[];
}

export async function fetchCountries(
  filters: CountryFilters,
  signal?: AbortSignal
): Promise<Country[]> {
  const params = new URLSearchParams({
    locale: filters.locale,
    max_budget: String(filters.maxBudget),
    min_safety_rating: String(filters.minSafety),
  });

  const res = await fetch(
    `${getApiBaseUrl()}/api/v1/countries?${params.toString()}`,
    {
      signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to load countries (${res.status})`);
  }

  return (await res.json()) as Country[];
}

export async function searchDestinations(
  payload: SearchRequest,
  signal?: AbortSignal
): Promise<SearchResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/search`, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail
        ? `Search failed (${res.status}): ${detail}`
        : `Search failed (${res.status})`
    );
  }

  return (await res.json()) as SearchResponse;
}

export async function generateItinerary(
  payload: ItineraryRequest,
  signal?: AbortSignal
): Promise<ItineraryResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/itineraries/generate`, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(await formatApiError(res, "Itinerary generation failed"));
  }

  return (await res.json()) as ItineraryResponse;
}

export type SavedItinerary = {
  id: string;
  user_id: string;
  title: string;
  destination: string;
  city_id?: string | null;
  days_data: unknown;
  total_cost_usd?: number | null;
  agent_reasoning?: string | null;
  created_at: string;
};

export async function saveItinerary(
  payload: {
    title: string;
    destination: string;
    city_id?: string;
    days_data: unknown;
    total_cost_usd?: number;
    agent_reasoning?: string;
  },
  accessToken: string,
  signal?: AbortSignal
): Promise<SavedItinerary> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/itineraries`, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await formatApiError(res, "Failed to save itinerary"));
  }
  return (await res.json()) as SavedItinerary;
}

export async function listSavedItineraries(
  accessToken: string,
  signal?: AbortSignal
): Promise<{ items: SavedItinerary[]; count: number }> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/itineraries`, {
    signal,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await formatApiError(res, "Failed to load saved itineraries"));
  }
  return (await res.json()) as { items: SavedItinerary[]; count: number };
}

async function formatApiError(res: Response, fallback: string): Promise<string> {
  const raw = await res.text().catch(() => "");
  if (!raw) {
    return `${fallback} (${res.status})`;
  }
  try {
    const parsed = JSON.parse(raw) as {
      detail?: string | { message?: string; violations?: string[] };
    };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      return `${fallback} (${res.status}): ${detail}`;
    }
    if (detail && typeof detail === "object") {
      const message = detail.message || fallback;
      const violations = detail.violations?.length
        ? ` — ${detail.violations.join("; ")}`
        : "";
      return `${message}${violations}`;
    }
  } catch {
    // not JSON
  }
  return `${fallback} (${res.status}): ${raw}`;
}

export function matchPercent(score: number): number {
  const pct = score <= 1 ? score * 100 : score;
  return Math.max(0, Math.min(100, Math.round(pct)));
}

export function emptyReasonMessage(reason: string | null | undefined): string {
  switch (reason) {
    case "BUDGET_TOO_LOW":
      return "No destinations fit this daily budget. Try raising the max budget.";
    case "SAFETY_TOO_STRICT":
      return "No destinations meet this minimum safety rating. Try lowering it.";
    case "NO_TAG_MATCH":
      return "No destinations match the selected tags with these filters.";
    case "NO_CANDIDATES":
      return "No destinations pass the current hard filters. Relax budget or safety.";
    default:
      return "No matching destinations. Adjust your query or sidebar filters.";
  }
}
