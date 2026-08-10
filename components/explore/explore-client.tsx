"use client";

import { useEffect, useState } from "react";

import { CountryCard } from "@/components/explore/country-card";
import { ExploreFilters } from "@/components/explore/explore-filters";
import {
  fetchCountries,
  type Country,
  type Locale,
} from "@/lib/api";

const DEFAULT_MAX_BUDGET = 200;
const DEFAULT_MIN_SAFETY = 3;
const DEFAULT_LOCALE: Locale = "en";

export function ExploreClient() {
  const [maxBudget, setMaxBudget] = useState(DEFAULT_MAX_BUDGET);
  const [debouncedBudget, setDebouncedBudget] = useState(DEFAULT_MAX_BUDGET);
  const [minSafety, setMinSafety] = useState(DEFAULT_MIN_SAFETY);
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE);
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedBudget(maxBudget), 250);
    return () => window.clearTimeout(timer);
  }, [maxBudget]);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
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
  }, [debouncedBudget, minSafety, locale]);

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

      <section className="min-w-0">
        <header className="mb-6 animate-fade-up">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            Explore
          </p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight text-[var(--foreground)] md:text-5xl">
            Travel Compass
          </h1>
          <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
            Browse countries that pass your budget and safety filters. Names and
            descriptions follow the active locale.
          </p>
        </header>

        <div className="mb-4 flex items-center justify-between gap-3 text-sm text-[var(--muted-foreground)]">
          <p>
            {loading
              ? "Loading destinations…"
              : `${countries.length} destination${countries.length === 1 ? "" : "s"}`}
          </p>
          {loading && (
            <span className="animate-soft-pulse text-[var(--primary)]">Updating</span>
          )}
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
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

        {!loading && !error && countries.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--card)]/70 px-6 py-12 text-center">
            <p className="font-[family-name:var(--font-display)] text-xl">
              No countries match these filters
            </p>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              Try raising the budget ceiling or lowering the minimum safety
              rating.
            </p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {countries.map((country, index) => (
            <CountryCard key={country.id} country={country} index={index} />
          ))}
        </div>
      </section>
    </div>
  );
}
