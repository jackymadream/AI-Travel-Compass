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
