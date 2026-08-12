"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import {
  itineraryDurationDays,
  listSavedItineraries,
  type SavedItinerary,
} from "@/lib/api";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

function formatCreatedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function ItinerariesClient() {
  const [items, setItems] = useState<SavedItinerary[]>([]);
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
          throw new Error("Sign in to view your itineraries.");
        }
        const data = await listSavedItineraries(token, controller.signal);
        if (!controller.signal.aborted) {
          setItems(data.items);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load itineraries");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 lg:px-8">
      <header className="animate-fade-up space-y-4">
        <SiteNav active="itineraries" />
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            Saved trips
          </p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight text-[var(--foreground)] md:text-5xl">
            My itineraries
          </h1>
          <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
            Re-open a saved plan or head back to the planner to draft another.
          </p>
        </div>
      </header>

      {loading && (
        <p className="mt-10 text-sm text-[var(--muted-foreground)]" role="status">
          Loading your trips…
        </p>
      )}

      {error && !loading && (
        <div
          className="mt-8 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          <p className="font-medium">Could not load itineraries</p>
          <p className="mt-1">{error}</p>
          <p className="mt-3">
            <Link href="/login?next=/itineraries" className="underline underline-offset-2">
              Sign in
            </Link>
          </p>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="mt-10 rounded-2xl border border-dashed border-[var(--border)] bg-[var(--card)]/60 px-6 py-14 text-center">
          <p className="font-[family-name:var(--font-display)] text-xl">
            No saved trips yet
          </p>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            Generate a plan in the planner, then tap Save itinerary.
          </p>
          <Button asChild className="mt-6" size="sm">
            <Link href="/planner">Open planner</Link>
          </Button>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <ul className="mt-10 grid gap-4 sm:grid-cols-2">
          {items.map((item) => {
            const days = itineraryDurationDays(item.days_data);
            return (
              <li
                key={item.id}
                className="flex flex-col justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 p-5 transition-colors hover:border-[var(--primary)]"
              >
                <div>
                  <h2 className="font-[family-name:var(--font-display)] text-xl tracking-tight">
                    {item.destination || item.title}
                  </h2>
                  <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                    {item.title}
                  </p>
                  <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-[var(--muted-foreground)]">Duration</dt>
                      <dd className="font-medium">
                        {days > 0 ? `${days} day${days === 1 ? "" : "s"}` : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[var(--muted-foreground)]">Saved</dt>
                      <dd className="font-medium">{formatCreatedAt(item.created_at)}</dd>
                    </div>
                  </dl>
                </div>
                <Button asChild size="sm" variant="secondary" className="w-fit">
                  <Link href={`/itineraries/${item.id}`}>View plan</Link>
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
