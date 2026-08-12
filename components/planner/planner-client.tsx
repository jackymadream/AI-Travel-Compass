"use client";

import { useEffect, useRef, useState } from "react";

import { AgentReasoningPanel } from "@/components/planner/agent-reasoning";
import { DayTimeline } from "@/components/planner/day-timeline";
import { PlannerControls } from "@/components/planner/planner-controls";
import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import {
  PLANNER_CITIES,
  fetchCities,
  generateItinerary,
  saveItinerary,
  type CitySummary,
  type ItineraryResponse,
  type Locale,
  type TripPace,
} from "@/lib/api";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

const LOADING_MESSAGE =
  "Agent is querying POIs and optimizing budget…";

export function PlannerClient() {
  const [cities, setCities] = useState<CitySummary[]>([]);
  const [cityId, setCityId] = useState<string>(PLANNER_CITIES[0].id);
  const [days, setDays] = useState(3);
  const [pace, setPace] = useState<TripPace>("moderate");
  const [dailyBudget, setDailyBudget] = useState(100);
  const [preferences, setPreferences] = useState<string[]>(["food", "culture"]);
  const [locale, setLocale] = useState<Locale>("en");

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ItineraryResponse | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchCities(locale, controller.signal)
      .then((rows) => {
        if (controller.signal.aborted || !rows.length) return;
        setCities(rows);
        const tokyo = rows.find((c) => c.slug === "tokyo");
        const preferred = tokyo ?? rows[0];
        setCityId(preferred.id);
      })
      .catch(() => {
        /* keep mock PLANNER_CITIES */
      });
    return () => controller.abort();
  }, [locale]);

  async function handleGenerate() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setSaveMessage(null);

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
    if (!result) return;
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
      const saved = await saveItinerary(
        {
          title: `${result.city_name} — ${days} day plan`,
          destination: result.city_name,
          city_id: cityId,
          days_data: result.daily_plans,
          total_cost_usd: result.total_cost_usd,
          agent_reasoning: result.agent_reasoning,
        },
        token
      );
      setSaveMessage(`Saved itinerary ${saved.id.slice(0, 8)}…`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 lg:grid-cols-[300px_1fr] lg:px-8">
      <PlannerControls
        cityId={cityId}
        cities={cities}
        days={days}
        pace={pace}
        dailyBudget={dailyBudget}
        preferences={preferences}
        locale={locale}
        loading={loading}
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
          <SiteNav active="planner" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
              Itinerary planner
            </p>
            <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight text-[var(--foreground)] md:text-5xl">
              Day-by-day with the agent
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
              Set days, pace, and budget. The agent retrieves grounded POIs,
              evaluates the schedule, and returns a validated timeline.
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
              , then try again with a higher budget or fewer days.
            </p>
          </div>
        )}

        {saveMessage && (
          <p className="text-sm text-[var(--primary)]" role="status">
            {saveMessage}
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
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-[family-name:var(--font-display)] text-2xl">
                  {result.city_name} timeline
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm text-[var(--muted-foreground)]">
                    Trip total ${result.total_cost_usd.toFixed(0)}
                  </p>
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
                </div>
              </div>
              <DayTimeline days={result.daily_plans} />
            </div>
            <AgentReasoningPanel
              response={result}
              className="h-fit xl:sticky xl:top-8"
            />
          </div>
        )}
      </section>
    </div>
  );
}
