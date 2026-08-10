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

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || DEFAULT_API_BASE
  );
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
