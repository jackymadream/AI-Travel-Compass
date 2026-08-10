"use client";

import { useEffect, useState } from "react";

import { AiSearchBar } from "@/components/explore/ai-search-bar";
import { DestinationCard } from "@/components/explore/country-card";
import { ExploreFilters } from "@/components/explore/explore-filters";
import {
  emptyReasonMessage,
  fetchCountries,
  searchDestinations,
  type Country,
  type Locale,
  type SearchHit,
} from "@/lib/api";

const DEFAULT_MAX_BUDGET = 200;
const DEFAULT_MIN_SAFETY = 3;
const DEFAULT_LOCALE: Locale = "en";

type Mode = "browse" | "search";

export function ExploreClient() {
  const [maxBudget, setMaxBudget] = useState(DEFAULT_MAX_BUDGET);
  const [debouncedBudget, setDebouncedBudget] = useState(DEFAULT_MAX_BUDGET);
  const [minSafety, setMinSafety] = useState(DEFAULT_MIN_SAFETY);
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE);

  const [mode, setMode] = useState<Mode>("browse");
  const [activeQuery, setActiveQuery] = useState("");

  const [countries, setCountries] = useState<Country[]>([]);
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedBudget(maxBudget), 250);
    return () => window.clearTimeout(timer);
  }, [maxBudget]);

  // Browse mode: countries list follows sidebar filters
  useEffect(() => {
    if (mode !== "browse") return;

    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      setEmptyReason(null);
      try {
        const data = await fetchCountries(
          {
            locale,
            maxBudget: debouncedBudget,
            minSafety,
          },
          controller.signal
        );
        setCountries(data);
      } catch (err) {
        if (controller.signal.aborted) return;
        setCountries([]);
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load countries from the API."
        );
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [mode, debouncedBudget, minSafety, locale]);

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
  }

  function handleClearSearch() {
    setMode("browse");
    setActiveQuery("");
    setSearchHits([]);
    setEmptyReason(null);
  }

  const resultCount = mode === "search" ? searchHits.length : countries.length;

  return (
    <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 lg:grid-cols-[280px_1fr] lg:px-8">
      <ExploreFilters
        maxBudget={maxBudget}
        minSafety={minSafety}
        locale={locale}
        onMaxBudgetChange={setMaxBudget}
        onMinSafetyChange={setMinSafety}
        onLocaleChange={setLocale}
      />

      <section className="min-w-0 space-y-6">
        <header className="animate-fade-up">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            Explore
          </p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight text-[var(--foreground)] md:text-5xl">
            Travel Compass
          </h1>
          <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
            Describe your trip in natural language, or browse with hard filters.
            Budget, safety, and locale always apply before ranking.
          </p>
        </header>

        <AiSearchBar
          initialQuery={activeQuery}
          loading={loading && mode === "search"}
          onSearch={handleSearch}
          onClear={handleClearSearch}
        />

        <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted-foreground)]">
          <p>
            {loading
              ? mode === "search"
                ? "Searching destinations…"
                : "Loading destinations…"
              : mode === "search"
                ? `${resultCount} AI match${resultCount === 1 ? "" : "es"}`
                : `${resultCount} destination${resultCount === 1 ? "" : "s"}`}
          </p>
          {loading && (
            <span className="animate-soft-pulse text-[var(--primary)]">
              Updating
            </span>
          )}
        </div>

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

        {!loading && !error && resultCount === 0 && (
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
            ? searchHits.map((hit, index) => (
                <DestinationCard
                  key={hit.city_id ?? `${hit.name}-${index}`}
                  hit={hit}
                  index={index}
                />
              ))
            : countries.map((country, index) => (
                <DestinationCard
                  key={country.id}
                  country={country}
                  index={index}
                />
              ))}
        </div>
      </section>
    </div>
  );
}
