"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DayTimeline } from "@/components/planner/day-timeline";
import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import {
  asDailyPlans,
  getSavedItinerary,
  itineraryDurationDays,
  type SavedItinerary,
} from "@/lib/api";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

type ItineraryDetailClientProps = {
  itineraryId: string;
};

export function ItineraryDetailClient({ itineraryId }: ItineraryDetailClientProps) {
  const [item, setItem] = useState<SavedItinerary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (!isSupabaseConfigured()) {
          throw new Error("Sign-in is not configured (missing Supabase public env).");
        }
        const supabase = createClient();
        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData.session?.access_token;
        if (!token) {
          throw new Error("Sign in to view this itinerary.");
        }
        const data = await getSavedItinerary(itineraryId, token, controller.signal);
        if (!controller.signal.aborted) {
          setItem(data);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load itinerary");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [itineraryId]);

  const days = item ? asDailyPlans(item.days_data) : [];
  const duration = item ? itineraryDurationDays(item.days_data) : 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 lg:px-8">
      <header className="animate-fade-up space-y-4">
        <SiteNav active="itineraries" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
              Saved itinerary
            </p>
            <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight">
              {item?.destination || "Trip plan"}
            </h1>
            {item && (
              <p className="mt-2 text-[var(--muted-foreground)]">
                {item.title}
                {duration > 0 ? ` · ${duration} day${duration === 1 ? "" : "s"}` : ""}
                {item.total_cost_usd != null
                  ? ` · ~$${Number(item.total_cost_usd).toFixed(0)}`
                  : ""}
              </p>
            )}
          </div>
          <Button asChild size="sm" variant="secondary">
            <Link href="/itineraries">All itineraries</Link>
          </Button>
        </div>
      </header>

      {loading && (
        <p className="mt-10 text-sm text-[var(--muted-foreground)]" role="status">
          Loading plan…
        </p>
      )}

      {error && !loading && (
        <div
          className="mt-8 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          <p className="font-medium">Could not load this plan</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {item && !loading && (
        <div className="mt-10 space-y-8">
          {item.agent_reasoning && (
            <aside className="rounded-2xl border border-[var(--border)] bg-[var(--card)]/80 px-5 py-4 text-sm text-[var(--muted-foreground)]">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground)]">
                Agent notes
              </p>
              <p className="mt-2 whitespace-pre-wrap">{item.agent_reasoning}</p>
            </aside>
          )}
          {days.length > 0 ? (
            <DayTimeline days={days} />
          ) : (
            <p className="text-sm text-[var(--muted-foreground)]">
              This save has no day timeline data.
            </p>
          )}
          <Button asChild size="sm">
            <Link href="/planner">Plan another trip</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
