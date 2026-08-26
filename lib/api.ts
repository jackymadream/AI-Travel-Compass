export type Locale = "en" | "zh-HK" | "ja";

export type BestTravelSeason = {
  seasons: string[];
  months: number[];
  label: string;
};

export type TopCity = {
  slug: string;
  name: string;
  photo_url?: string | null;
  description?: string;
  tags?: string[];
};

export type Country = {
  id: string;
  iso_code: string;
  slug?: string | null;
  name: string;
  description: string;
  safety_index: number;
  avg_daily_cost_usd: number;
  best_travel_season: BestTravelSeason;
  best_season?: string;
  region_tags: string[];
  tags?: string[];
  photo_url?: string | null;
  top_cities?: TopCity[];
};

export type CountryFilters = {
  locale: Locale;
  maxBudget: number;
  minSafety: number;
  tags?: string[];
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
  is_food_slot?: boolean;
  meal_role?: "lunch" | "dinner" | null;
  lat?: number | null;
  lon?: number | null;
  poi_id?: string | null;
  address?: string | null;
  photo_url?: string | null;
  display_name?: string | null;
  is_custom?: boolean;
};

export type DailyItinerary = {
  day_number: number;
  theme: string;
  estimated_daily_cost: number;
  activities: Activity[];
  warnings?: string[];
};

export type ItineraryResponse = {
  city_name: string;
  total_cost_usd: number;
  daily_plans: DailyItinerary[];
  agent_reasoning: string;
  user_summary?: string | null;
  prep_tips?: string[];
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
  country_id?: string | null;
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
  signal?: AbortSignal,
  limit = 200
): Promise<CitySummary[]> {
  const params = new URLSearchParams({ locale, limit: String(limit) });
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
  for (const tag of filters.tags ?? []) {
    const cleaned = tag.trim();
    if (cleaned) params.append("tags", cleaned);
  }

  // Bust any intermediary HTTP caches (stale photo_url payloads caused
  // a race where an older response overwrote a fresh one in Explore).
  params.set("_cb", String(Date.now()));

  const res = await fetch(
    `${getApiBaseUrl()}/api/v1/countries?${params.toString()}`,
    {
      signal,
      headers: {
        Accept: "application/json",
        "Cache-Control": "no-cache",
        Pragma: "no-cache",
      },
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

export type ItineraryProgressEvent = {
  step: string;
  percent: number;
  day_number?: number;
  total_days?: number;
  turn?: number;
};

/** Stream SSE progress events, then return the validated itinerary. */
export async function generateItineraryWithProgress(
  payload: ItineraryRequest,
  onProgress: (event: ItineraryProgressEvent) => void,
  signal?: AbortSignal
): Promise<ItineraryResponse> {
  const res = await fetch(
    `${getApiBaseUrl()}/api/v1/itineraries/generate/stream`,
    {
      method: "POST",
      signal,
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(await formatApiError(res, "Itinerary generation failed"));
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("Streaming is not supported in this browser.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const normalized = buffer.replace(/\r\n/g, "\n");
    const chunks = normalized.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data: ")) continue;
      const data = JSON.parse(line.slice(6)) as {
        type: string;
        step?: string;
        percent?: number;
        day_number?: number;
        total_days?: number;
        turn?: number;
        result?: ItineraryResponse;
        message?: string;
      };
      if (
        data.type === "progress" &&
        data.step != null &&
        data.percent != null
      ) {
        onProgress({
          step: data.step,
          percent: data.percent,
          day_number: data.day_number,
          total_days: data.total_days,
          turn: data.turn,
        });
      } else if (data.type === "complete" && data.result) {
        return data.result;
      } else if (data.type === "error") {
        throw new Error(data.message ?? "Itinerary generation failed");
      }
    }
  }

  throw new Error("Itinerary stream ended without a result.");
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

export async function updateItinerary(
  itineraryId: string,
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
  const res = await fetch(
    `${getApiBaseUrl()}/api/v1/itineraries/${encodeURIComponent(itineraryId)}`,
    {
      method: "PUT",
      signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    }
  );
  if (!res.ok) {
    throw new Error(await formatApiError(res, "Failed to update itinerary"));
  }
  return (await res.json()) as SavedItinerary;
}

export async function getSavedItinerary(
  itineraryId: string,
  accessToken: string,
  signal?: AbortSignal
): Promise<SavedItinerary> {
  const res = await fetch(
    `${getApiBaseUrl()}/api/v1/itineraries/${encodeURIComponent(itineraryId)}`,
    {
      signal,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
    }
  );
  if (!res.ok) {
    throw new Error(await formatApiError(res, "Failed to load itinerary"));
  }
  return (await res.json()) as SavedItinerary;
}

export function itineraryDurationDays(daysData: unknown): number {
  if (Array.isArray(daysData)) {
    return daysData.length;
  }
  if (
    daysData &&
    typeof daysData === "object" &&
    Array.isArray((daysData as { daily_plans?: unknown }).daily_plans)
  ) {
    return ((daysData as { daily_plans: unknown[] }).daily_plans).length;
  }
  return 0;
}

export function asDailyPlans(daysData: unknown): DailyItinerary[] {
  if (Array.isArray(daysData)) {
    return daysData as DailyItinerary[];
  }
  if (
    daysData &&
    typeof daysData === "object" &&
    Array.isArray((daysData as { daily_plans?: unknown }).daily_plans)
  ) {
    return (daysData as { daily_plans: DailyItinerary[] }).daily_plans;
  }
  return [];
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

/**
 * Honest match % from hybrid ranking score.
 * Scores in [0, 1] map linearly to 0–100; values already on a 0–100 scale are clamped.
 * Weak matches stay low — do not inflate into a 70–99 band.
 */
export function matchPercent(score: number): number {
  if (!Number.isFinite(score)) return 0;
  const unit = score <= 1 ? score : score / 100;
  return Math.max(0, Math.min(100, Math.round(unit * 100)));
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
