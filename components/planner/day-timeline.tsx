"use client";

import { MapPin, Timer } from "lucide-react";

import type { Activity, ActivityCategory, DailyItinerary } from "@/lib/api";
import { cn } from "@/lib/utils";

const CATEGORY_STYLES: Record<
  ActivityCategory,
  { label: string; className: string }
> = {
  attraction: {
    label: "Attraction",
    className: "bg-[#d7ebe4] text-[#1a3a33]",
  },
  food: {
    label: "Food",
    className: "bg-[#f3e0d4] text-[#7a3b16]",
  },
  rest: {
    label: "Rest",
    className: "bg-[#e4e8f0] text-[#334155]",
  },
};

type DayTimelineProps = {
  days: DailyItinerary[];
};

export function DayTimeline({ days }: DayTimelineProps) {
  return (
    <div className="space-y-8">
      {days.map((day, index) => (
        <section
          key={day.day_number}
          className="animate-fade-up"
          style={{ animationDelay: `${index * 70}ms` }}
        >
          <header className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-[var(--border)] pb-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Day {day.day_number}
              </p>
              <h3 className="mt-1 font-[family-name:var(--font-display)] text-2xl text-[var(--foreground)]">
                {day.theme}
              </h3>
            </div>
            <p className="rounded-full bg-[var(--secondary)] px-3 py-1 text-sm font-medium text-[var(--secondary-foreground)]">
              Day total ${day.estimated_daily_cost.toFixed(0)}
            </p>
          </header>

          <ol className="relative space-y-0 border-l-2 border-[var(--border)] pl-6">
            {day.activities.map((activity, activityIndex) => (
              <TimelineItem
                key={`${day.day_number}-${activity.poi_name}-${activityIndex}`}
                activity={activity}
                isLast={activityIndex === day.activities.length - 1}
              />
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

function TimelineItem({
  activity,
  isLast,
}: {
  activity: Activity;
  isLast: boolean;
}) {
  const badge = CATEGORY_STYLES[activity.category];

  return (
    <li className={cn("relative pb-6", isLast && "pb-0")}>
      <span
        className="absolute -left-[1.9rem] top-1.5 h-3 w-3 rounded-full border-2 border-[var(--primary)] bg-[var(--card)]"
        aria-hidden
      />
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)]/80 p-4 transition-colors hover:border-[var(--primary)]/50">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
              {activity.time_slot}
            </p>
            <h4 className="flex items-start gap-2 font-medium text-[var(--foreground)]">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary)]" />
              <span>{activity.poi_name}</span>
            </h4>
          </div>
          <span
            className={cn(
              "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
              badge.className
            )}
          >
            {badge.label}
          </span>
        </div>

        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          {activity.description}
        </p>

        <div className="mt-3 flex flex-wrap gap-3 text-xs text-[var(--muted-foreground)]">
          <span className="inline-flex items-center gap-1">
            <Timer className="h-3.5 w-3.5" />
            {activity.duration_minutes} min
          </span>
          <span>${activity.cost_usd.toFixed(0)}</span>
        </div>
      </div>
    </li>
  );
}
