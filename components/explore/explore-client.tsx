"use client";

import { useEffect, useMemo, useState } from "react";

import { AiSearchBar } from "@/components/explore/ai-search-bar";
import { CountryBrowseCard } from "@/components/explore/country-card";
import { ExploreFilters } from "@/components/explore/explore-filters";
import { SiteNav } from "@/components/site-nav";
import { useLocale } from "@/components/locale-provider";
import { useTranslations } from "next-intl";
import {
  emptyReasonMessage,
  fetchCities,
  fetchCountries,
  matchPercent,
  searchDestinations,
  type CitySummary,
  type Country,
  type SearchHit,
} from "@/lib/api";

const DEFAULT_MAX_BUDGET = 200;
const DEFAULT_MIN_SAFETY = 3;

type Mode = "browse" | "search";

export function ExploreClient() {
  const { locale, setLocale } = useLocale();
  const t = useTranslations("explore");
  const [maxBudget, setMaxBudget] = useState(DEFAULT_MAX_BUDGET);
  const [debouncedBudget, setDebouncedBudget] = useState(DEFAULT_MAX_BUDGET);
  const [minSafety, setMinSafety] = useState(DEFAULT_MIN_SAFETY);

  const [mode, setMode] = useState<Mode>("browse");
  const [activeQuery, setActiveQuery] = useState("");

  const [countries, setCountries] = useState<Country[]>([]);
  const [countryCatalog, setCountryCatalog] = useState<Country[]>([]);
  const [cities, setCities] = useState<CitySummary[]>([]);
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);
  const [expandedCountryId, setExpandedCountryId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedBudget(maxBudget), 250);
    return () => window.clearTimeout(timer);
  }, [maxBudget]);

  // Resolve city UUIDs for Plan Trip links (top_cities only have slugs).
  useEffect(() => {
    const controller = new AbortController();
    void fetchCities(locale, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) setCities(rows);
      })
      .catch(() => {
        if (!controller.signal.aborted) setCities([]);
      });
    return () => controller.abort();
  }, [locale]);

  const resolveCityId = useMemo(() => {
    const byCountrySlug = new Map<string, string>();
    for (const city of cities) {
      if (city.country_id) {
        byCountrySlug.set(`${city.country_id}:${city.slug}`, city.id);
      }
    }
    return (countryId: string, citySlug: string) =>
      byCountrySlug.get(`${countryId}:${citySlug}`) ?? null;
  }, [cities]);

  // Country catalog follows sidebar filters (browse display + search enrichment)
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      if (mode === "browse") {
        setLoading(true);
        setError(null);
        setEmptyReason(null);
      }
      try {
        const data = await fetchCountries(
          {
            locale,
            maxBudget: debouncedBudget,
            minSafety,
          },
          controller.signal
        );
        if (cancelled) return;
        setCountries(data);
      } catch (err) {
        if (cancelled || controller.signal.aborted) return;
        setCountries([]);
        if (mode === "browse") {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load countries from the API."
          );
        }
      } finally {
        if (
          mode === "browse" &&
          !cancelled &&
          !controller.signal.aborted
        ) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [mode, debouncedBudget, minSafety, locale]);

  // Wide catalog so AI city hits can resolve to full country cards (photo / cities)
  useEffect(() => {
    if (mode !== "search") return;
    const controller = new AbortController();
    void fetchCountries(
      { locale, maxBudget: 500, minSafety: 1 },
      controller.signal
    )
      .then((rows) => {
        if (!controller.signal.aborted) setCountryCatalog(rows);
      })
      .catch(() => {
        if (!controller.signal.aborted) setCountryCatalog([]);
      });
    return () => controller.abort();
  }, [mode, locale]);

  // Search mode: re-run AI search when sidebar filters / locale change
  useEffect(() => {
    if (mode !== "search" || !activeQuery.trim()) return;

    const controller = new AbortController();

    async function runSearch() {
      setLoading(true);
      setError(null);
      try {
        const data = await searchDestinations(
          {
            query: activeQuery,
            locale,
            max_budget: debouncedBudget,
            min_safety: minSafety,
            limit: 12,
          },
          controller.signal
        );
        setSearchHits(data.results);
        setEmptyReason(data.empty_reason);
      } catch (err) {
        if (controller.signal.aborted) return;
        setSearchHits([]);
        setEmptyReason(null);
        setError(
          err instanceof Error ? err.message : "Unable to run AI search."
        );
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void runSearch();
    return () => controller.abort();
  }, [mode, activeQuery, debouncedBudget, minSafety, locale]);

  function handleSearch(query: string) {
    setMode("search");
    setActiveQuery(query);
    setExpandedCountryId(null);
  }

  function handleClearSearch() {
    setMode("browse");
    setActiveQuery("");
    setSearchHits([]);
    setEmptyReason(null);
  }

  /** AI hits are cities — map to unique countries (best score) for browse cards. */
  const searchCountryResults = useMemo(() => {
    const catalog =
      countryCatalog.length > 0 ? countryCatalog : countries;
    const byId = new Map(catalog.map((c) => [c.id, c]));
    const byIso = new Map(
      catalog.map((c) => [c.iso_code.toUpperCase(), c])
    );
    const best = new Map<
      string,
      { country: Country; score: number; matchedTags: string[] }
    >();

    for (const hit of searchHits) {
      const country =
        (hit.country_id ? byId.get(hit.country_id) : undefined) ??
        (hit.iso_code ? byIso.get(hit.iso_code.toUpperCase()) : undefined);
      if (!country) continue;

      const prev = best.get(country.id);
      if (!prev || hit.score > prev.score) {
        best.set(country.id, {
          country,
          score: hit.score,
          matchedTags: hit.tags ?? [],
        });
      }
    }

    const ranked = [...best.values()].sort((a, b) => b.score - a.score);
    return ranked.map((r) => ({
      country: r.country,
      score: r.score,
      matchPercentValue: matchPercent(r.score),
      matchedTags: r.matchedTags,
    }));
  }, [searchHits, countries, countryCatalog]);

  const topMatchPercent =
    mode === "search" && searchCountryResults.length > 0
      ? searchCountryResults[0].matchPercentValue
      : null;
  const resultCount =
    mode === "search" ? searchCountryResults.length : countries.length;

  const enrichingSearch =
    mode === "search" &&
    !loading &&
    searchHits.length > 0 &&
    searchCountryResults.length === 0 &&
    countryCatalog.length === 0;

  const showLoading = loading || enrichingSearch;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-10 lg:px-8">
      <div className="lg:hidden">
        <SiteNav active="explore" />
      </div>

      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <ExploreFilters
          maxBudget={maxBudget}
          minSafety={minSafety}
          locale={locale}
          onMaxBudgetChange={setMaxBudget}
          onMinSafetyChange={setMinSafety}
          onLocaleChange={setLocale}
        />

        <section className="min-w-0 space-y-6">
          <header className="animate-fade-up space-y-4">
            <div className="hidden lg:block">
              <SiteNav active="explore" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
                {t("kicker")}
              </p>
              <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight text-[var(--foreground)] md:text-5xl">
                {t("title")}
              </h1>
              <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
                {t("subtitle")}
              </p>
            </div>
          </header>

        <AiSearchBar
          initialQuery={activeQuery}
          loading={showLoading && mode === "search"}
          placeholder={t("searchPlaceholder")}
          onSearch={handleSearch}
          onClear={handleClearSearch}
        />

        <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted-foreground)]">
          <p>
            {showLoading
              ? mode === "search"
                ? t("searching")
                : t("loading")
              : mode === "search"
                ? t(resultCount === 1 ? "matches" : "matchesPlural", {
                    count: resultCount,
                  })
                : t(
                    resultCount === 1 ? "destinations" : "destinationsPlural",
                    { count: resultCount }
                  )}
          </p>
          {showLoading && (
            <span className="animate-soft-pulse text-[var(--primary)]">
              {t("updating")}
            </span>
          )}
        </div>

        {mode === "search" &&
          !showLoading &&
          topMatchPercent != null &&
          topMatchPercent < 40 && (
            <p className="text-sm text-[var(--muted-foreground)]">
              Weak semantic match — try a more specific description (interests,
              vibe, or place type).
            </p>
          )}

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
            <p className="mt-1 text-red-700/80">
              Make sure FastAPI is running on{" "}
              <code className="rounded bg-red-100 px-1">
                {process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}
              </code>
              .
            </p>
          </div>
        )}

        {!showLoading && !error && resultCount === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--card)]/70 px-6 py-12 text-center">
            <p className="font-[family-name:var(--font-display)] text-xl">
              {mode === "search"
                ? "No destinations match this search"
                : "No countries match these filters"}
            </p>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              {mode === "search"
                ? emptyReasonMessage(emptyReason)
                : "Try raising the budget ceiling or lowering the minimum safety rating."}
            </p>
            {mode === "search" && emptyReason && (
              <p className="mt-3 text-xs uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                Reason: {emptyReason}
              </p>
            )}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {mode === "search"
            ? searchCountryResults.map(
                ({ country, matchPercentValue, matchedTags }, index) => (
                <CountryBrowseCard
                  key={country.id}
                  country={country}
                  index={index}
                  matchPercentValue={matchPercentValue}
                  highlightTags={matchedTags}
                  expanded={expandedCountryId === country.id}
                  muted={
                    expandedCountryId != null &&
                    expandedCountryId !== country.id
                  }
                  resolveCityId={resolveCityId}
                  onToggle={() =>
                    setExpandedCountryId((current) =>
                      current === country.id ? null : country.id
                    )
                  }
                />
              )
              )
            : countries.map((country, index) => (
                <CountryBrowseCard
                  key={country.id}
                  country={country}
                  index={index}
                  expanded={expandedCountryId === country.id}
                  muted={
                    expandedCountryId != null &&
                    expandedCountryId !== country.id
                  }
                  resolveCityId={resolveCityId}
                  onToggle={() =>
                    setExpandedCountryId((current) =>
                      current === country.id ? null : country.id
                    )
                  }
                />
              ))}
        </div>
      </section>
      </div>
    </div>
  );
}
