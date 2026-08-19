"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AgentReasoningPanel } from "@/components/planner/agent-reasoning";
import type { CustomSpotPayload } from "@/components/planner/custom-spot-dialog";
import { DayTimeline } from "@/components/planner/day-timeline";
import { ItineraryMapDynamic } from "@/components/planner/itinerary-map-dynamic";
import { PoiDetailDrawer } from "@/components/planner/poi-detail-drawer";
import { PlannerControls } from "@/components/planner/planner-controls";
import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import { useTranslations } from "next-intl";
import {
  PLANNER_CITIES,
  fetchCities,
  fetchCountries,
  generateItinerary,
  saveItinerary,
  type Activity,
  type CitySummary,
  type Country,
  type ItineraryResponse,
  type TripPace,
} from "@/lib/api";
import {
  insertCustomSpot,
  moveActivity,
  scheduleWarnings,
  tripTotal,
  updateActivity,
} from "@/lib/itinerary-edit";
import { DEFAULT_PLANNER_PREFERENCES } from "@/lib/planner-preferences";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { useLocale } from "@/components/locale-provider";

const LOADING_MESSAGE =
  "Agent is querying POIs and optimizing budget…";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function resolveCountryId(
  raw: string | null,
  countries: Country[],
  cities: CitySummary[]
): string | null {
  if (!raw) return null;
  if (UUID_RE.test(raw)) {
    if (countries.some((c) => c.id === raw)) return raw;
    const viaCity = cities.find((c) => c.country_id === raw);
    if (viaCity?.country_id) return viaCity.country_id;
  }
  const bySlug = countries.find(
    (c) => c.slug?.toLowerCase() === raw.toLowerCase()
  );
  if (bySlug) return bySlug.id;
  const byIso = countries.find(
    (c) => c.iso_code.toLowerCase() === raw.toLowerCase()
  );
  if (byIso) return byIso.id;
  return null;
}

function resolveCityId(
  raw: string | null,
  cities: CitySummary[],
  countryId: string | null
): string | null {
  if (!raw) return null;
  if (UUID_RE.test(raw)) {
    const byId = cities.find((c) => c.id === raw);
    if (byId) return byId.id;
  }
  const slug = raw.toLowerCase();
  const candidates = cities.filter((c) => c.slug.toLowerCase() === slug);
  if (countryId) {
    const scoped = candidates.find((c) => c.country_id === countryId);
    if (scoped) return scoped.id;
  }
  return candidates[0]?.id ?? null;
}

function PlannerClientInner() {
  const t = useTranslations("planner");
  const searchParams = useSearchParams();
  const [countries, setCountries] = useState<Country[]>([]);
  const [cities, setCities] = useState<CitySummary[]>([]);
  const [countryId, setCountryId] = useState<string>("");
  const [cityId, setCityId] = useState<string>(PLANNER_CITIES[0].id);
  const [days, setDays] = useState(3);
  const [pace, setPace] = useState<TripPace>("moderate");
  const [dailyBudget, setDailyBudget] = useState(100);
  const [preferences, setPreferences] = useState<string[]>([
    ...DEFAULT_PLANNER_PREFERENCES,
  ]);
  const { locale, setLocale } = useLocale();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ItineraryResponse | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState(1);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(
    null
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const queryAppliedRef = useRef(false);

  const cityCenter = useMemo(() => {
    if (!result) return null;
    for (const day of result.daily_plans) {
      for (const act of day.activities) {
        if (act.lat != null && act.lon != null) {
          return { lat: act.lat, lon: act.lon };
        }
      }
    }
    return null;
  }, [result]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      fetchCities(locale, controller.signal),
      fetchCountries(
        { locale, maxBudget: 500, minSafety: 1 },
        controller.signal
      ).catch(() => [] as Country[]),
    ])
      .then(([cityRows, countryRows]) => {
        if (controller.signal.aborted) return;
        setCities(cityRows);
        setCountries(countryRows);

        if (queryAppliedRef.current) {
          setCityId((current) => {
            if (cityRows.some((c) => c.id === current)) return current;
            return cityRows[0]?.id ?? PLANNER_CITIES[0].id;
          });
          return;
        }

        const qCity = searchParams.get("city");
        const qCountry = searchParams.get("country");
        let nextCountry = resolveCountryId(qCountry, countryRows, cityRows);
        let nextCity = resolveCityId(qCity, cityRows, nextCountry);

        if (!nextCity && qCity) {
          nextCity = resolveCityId(qCity, cityRows, null);
        }
        if (!nextCountry && nextCity) {
          nextCountry =
            cityRows.find((c) => c.id === nextCity)?.country_id ?? null;
        }
        if (!nextCity) {
          const tokyo = cityRows.find((c) => c.slug === "tokyo");
          nextCity = (tokyo ?? cityRows[0])?.id ?? PLANNER_CITIES[0].id;
        }
        if (!nextCountry) {
          nextCountry =
            cityRows.find((c) => c.id === nextCity)?.country_id ??
            countryRows[0]?.id ??
            "";
        }

        setCountryId(nextCountry || "");
        setCityId(nextCity);
        queryAppliedRef.current = true;
      })
      .catch(() => {
        /* keep mock PLANNER_CITIES */
      });
    return () => controller.abort();
  }, [locale, searchParams]);

  function selectActivity(
    activity: Activity,
    dayNumber: number,
    index: number
  ) {
    setSelectedDay(dayNumber);
    setSelectedKey(`${dayNumber}-${index}`);
    setSelectedActivity(activity);
    setDrawerOpen(true);
  }

  function addCustomSpot(dayNumber: number, spot: CustomSpotPayload) {
    setResult((prev) => {
      if (!prev) return prev;
      const daily_plans = insertCustomSpot(prev.daily_plans, dayNumber, spot);
      return { ...prev, daily_plans, total_cost_usd: tripTotal(daily_plans) };
    });
    setSavedId(null);
    setSaveMessage(null);
  }

  function handleMoveActivity(
    dayNumber: number,
    index: number,
    direction: -1 | 1
  ) {
    setResult((prev) => {
      if (!prev) return prev;
      const daily_plans = moveActivity(
        prev.daily_plans,
        dayNumber,
        index,
        direction
      );
      return { ...prev, daily_plans, total_cost_usd: tripTotal(daily_plans) };
    });
    setSavedId(null);
  }

  function handleUpdateActivity(
    dayNumber: number,
    index: number,
    patch: Partial<Activity>
  ) {
    setResult((prev) => {
      if (!prev) return prev;
      const daily_plans = updateActivity(
        prev.daily_plans,
        dayNumber,
        index,
        patch
      );
      return { ...prev, daily_plans, total_cost_usd: tripTotal(daily_plans) };
    });
    setSavedId(null);
    setSelectedActivity((current) =>
      current ? { ...current, ...patch } : current
    );
  }

  async function handleGenerate() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setSaveMessage(null);
    setSavedId(null);
    setDrawerOpen(false);
    setSelectedActivity(null);
    setSelectedKey(null);

    try {
      const data = await generateItinerary(
        {
          city_id: cityId,
          days,
          pace,
          daily_budget_usd: dailyBudget,
          preferences,
          locale,
        },
        controller.signal
      );
      if (!controller.signal.aborted) {
        setResult(data);
        setSelectedDay(data.daily_plans[0]?.day_number ?? 1);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setResult(null);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate an itinerary from the agent."
      );
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }

  async function handleSave() {
    if (!result || savedId) return;
    setSaving(true);
    setSaveMessage(null);
    setError(null);
    try {
      if (!isSupabaseConfigured()) {
        throw new Error("Sign-in is not configured (missing Supabase public env).");
      }
      const supabase = createClient();
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token;
      if (!token) {
        throw new Error("Sign in to save itineraries.");
      }
      const payload = {
        title: `${result.city_name} — ${days} day plan`,
        destination: result.city_name,
        city_id: cityId,
        days_data: result.daily_plans,
        total_cost_usd: result.total_cost_usd,
        agent_reasoning: result.agent_reasoning,
      };
      const saved = await saveItinerary(payload, token);
      setSavedId(saved.id);
      setSaveMessage("Saved ✓");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-10 lg:px-8">
      <div className="lg:hidden">
        <SiteNav active="planner" />
      </div>

      <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
        <PlannerControls
          countryId={countryId}
          cityId={cityId}
          countries={countries}
          cities={cities}
          days={days}
          pace={pace}
          dailyBudget={dailyBudget}
          preferences={preferences}
          locale={locale}
          loading={loading}
          onCountryIdChange={setCountryId}
          onCityIdChange={setCityId}
          onDaysChange={setDays}
          onPaceChange={setPace}
          onDailyBudgetChange={setDailyBudget}
          onPreferencesChange={setPreferences}
          onLocaleChange={setLocale}
          onGenerate={() => {
            void handleGenerate();
          }}
        />

        <section className="min-w-0 space-y-6">
          <header className="animate-fade-up space-y-4">
            <div className="hidden lg:block">
              <SiteNav active="planner" />
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

          {loading && (
            <div
              className="animate-fade-up rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 px-5 py-6"
              role="status"
              aria-live="polite"
            >
              <p className="animate-soft-pulse font-medium text-[var(--primary)]">
                {LOADING_MESSAGE}
              </p>
              <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                Retrieving attractions, food, and rest stops, then checking pace
                and daily spend.
              </p>
            </div>
          )}

          {error && !loading && (
            <div
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
              role="alert"
            >
              <p className="font-medium">Could not generate itinerary</p>
              <p className="mt-1 whitespace-pre-wrap text-red-700/90">{error}</p>
              <p className="mt-2 text-red-700/80">
                Confirm FastAPI is running on{" "}
                <code className="rounded bg-red-100 px-1">
                  {process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}
                </code>
                , then try again with a higher budget, fewer days, or a looser
                pace.
              </p>
            </div>
          )}

          {saveMessage && (
            <p className="text-sm text-[var(--primary)]" role="status">
              {saveMessage}
              {savedId ? (
                <>
                  {" — "}
                  <a
                    href="/itineraries"
                    className="underline underline-offset-2"
                  >
                    My itineraries
                  </a>
                </>
              ) : null}
            </p>
          )}

          {!loading && !error && !result && (
            <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--card)]/60 px-6 py-14 text-center">
              <p className="font-[family-name:var(--font-display)] text-xl">
                Ready when you are
              </p>
              <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                Choose a city and tap Generate itinerary to see the day-by-day
                timeline.
              </p>
            </div>
          )}

          {result && !loading && (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
              <div className="min-w-0 space-y-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="font-[family-name:var(--font-display)] text-2xl">
                    {result.city_name} timeline
                  </h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm text-[var(--muted-foreground)]">
                      Trip total ${result.total_cost_usd.toFixed(0)}
                    </p>
                    {savedId ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled
                        aria-label="Itinerary already saved"
                      >
                        Saved ✓
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={saving}
                        onClick={() => {
                          void handleSave();
                        }}
                      >
                        {saving ? "Saving…" : "Save itinerary"}
                      </Button>
                    )}
                  </div>
                </div>

                <ItineraryMapDynamic
                  days={result.daily_plans}
                  selectedDay={selectedDay}
                  onSelectedDayChange={setSelectedDay}
                  selectedKey={selectedKey}
                  onSelectActivity={selectActivity}
                  onAddCustomSpot={addCustomSpot}
                  cityCenter={cityCenter}
                  cityHint={result.city_name}
                />

                <DayTimeline
                  days={result.daily_plans}
                  selectedKey={selectedKey}
                  onSelectActivity={selectActivity}
                  editable
                  warnings={scheduleWarnings(result.daily_plans, dailyBudget)}
                  onMoveActivity={handleMoveActivity}
                />
              </div>
              <AgentReasoningPanel
                response={result}
                className="h-fit xl:sticky xl:top-8"
              />
            </div>
          )}
        </section>
      </div>

      <PoiDetailDrawer
        activity={selectedActivity}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSave={(patch) => {
          if (!selectedKey) return;
          const [dayPart, indexPart] = selectedKey.split("-");
          handleUpdateActivity(
            Number(dayPart),
            Number(indexPart),
            patch
          );
        }}
      />
    </div>
  );
}

export function PlannerClient() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-10 text-sm text-[var(--muted-foreground)]">
          Loading planner…
        </div>
      }
    >
      <PlannerClientInner />
    </Suspense>
  );
}
