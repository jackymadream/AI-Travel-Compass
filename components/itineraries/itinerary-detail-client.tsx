"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { CustomSpotPayload } from "@/components/planner/custom-spot-dialog";
import { DayTimeline } from "@/components/planner/day-timeline";
import { ItineraryMapDynamic } from "@/components/planner/itinerary-map-dynamic";
import { PoiDetailDrawer } from "@/components/planner/poi-detail-drawer";
import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import {
  asDailyPlans,
  getSavedItinerary,
  itineraryDurationDays,
  type Activity,
  type DailyItinerary,
  type SavedItinerary,
} from "@/lib/api";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

type ItineraryDetailClientProps = {
  itineraryId: string;
};

export function ItineraryDetailClient({
  itineraryId,
}: ItineraryDetailClientProps) {
  const [item, setItem] = useState<SavedItinerary | null>(null);
  const [days, setDays] = useState<DailyItinerary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState(1);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(
    null
  );
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (!isSupabaseConfigured()) {
          throw new Error(
            "Sign-in is not configured (missing Supabase public env)."
          );
        }
        const supabase = createClient();
        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData.session?.access_token;
        if (!token) {
          throw new Error("Sign in to view this itinerary.");
        }
        const data = await getSavedItinerary(
          itineraryId,
          token,
          controller.signal
        );
        if (!controller.signal.aborted) {
          setItem(data);
          const plans = asDailyPlans(data.days_data);
          setDays(plans);
          setSelectedDay(plans[0]?.day_number ?? 1);
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

  const duration = item ? itineraryDurationDays(item.days_data) : 0;
  const cityCenter = useMemo(() => {
    for (const day of days) {
      for (const act of day.activities) {
        if (act.lat != null && act.lon != null) {
          return { lat: act.lat, lon: act.lon };
        }
      }
    }
    return null;
  }, [days]);

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
    setDays((prev) =>
      prev.map((day) => {
        if (day.day_number !== dayNumber) return day;
        const custom: Activity = {
          time_slot: "Flexible",
          poi_name: spot.name,
          category: "attraction",
          cost_usd: 0,
          duration_minutes: 45,
          description: spot.address
            ? `Custom waypoint — ${spot.address}`
            : "Custom waypoint added on the map.",
          lat: spot.lat,
          lon: spot.lon,
          address: spot.address ?? null,
          is_custom: true,
          is_food_slot: false,
          meal_role: null,
        };
        return { ...day, activities: [...day.activities, custom] };
      })
    );
  }

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
                {duration > 0
                  ? ` · ${duration} day${duration === 1 ? "" : "s"}`
                  : ""}
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
        <p
          className="mt-10 text-sm text-[var(--muted-foreground)]"
          role="status"
        >
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
            <>
              <ItineraryMapDynamic
                days={days}
                selectedDay={selectedDay}
                onSelectedDayChange={setSelectedDay}
                selectedKey={selectedKey}
                onSelectActivity={selectActivity}
                onAddCustomSpot={addCustomSpot}
                cityCenter={cityCenter}
              />
              <DayTimeline
                days={days}
                selectedKey={selectedKey}
                onSelectActivity={selectActivity}
              />
            </>
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

      <PoiDetailDrawer
        activity={selectedActivity}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
