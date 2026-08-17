"use client";

import { MapPin, Timer } from "lucide-react";

import type { Activity, DailyItinerary } from "@/lib/api";
import { ActivityPhoto } from "@/components/planner/activity-photo";
import { activityBadgeStyle } from "@/lib/planner-styles";
import { cn } from "@/lib/utils";

type DayTimelineProps = {
  days: DailyItinerary[];
  selectedKey?: string | null;
  onSelectActivity?: (
    activity: Activity,
    dayNumber: number,
    index: number
  ) => void;
};

export function DayTimeline({
  days,
  selectedKey = null,
  onSelectActivity,
}: DayTimelineProps) {
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
                selected={selectedKey === `${day.day_number}-${activityIndex}`}
                onSelect={
                  onSelectActivity
                    ? () =>
                        onSelectActivity(
                          activity,
                          day.day_number,
                          activityIndex
                        )
                    : undefined
                }
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
  selected,
  onSelect,
}: {
  activity: Activity;
  isLast: boolean;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const badge = activityBadgeStyle(activity);
  const label = activity.is_food_slot
    ? activity.meal_role === "dinner"
      ? "Dinner"
      : "Lunch"
    : badge.label;

  const content = (
    <>
      <span
        className="absolute -left-[1.9rem] top-1.5 h-3 w-3 rounded-full border-2 border-[var(--primary)] bg-[var(--card)]"
        aria-hidden
      />
      <div
        className={cn(
          "overflow-hidden rounded-xl border bg-[var(--card)]/80 transition-colors",
          selected
            ? "border-[var(--primary)] ring-1 ring-[var(--primary)]/40"
            : "border-[var(--border)] hover:border-[var(--primary)]/50",
          onSelect && "cursor-pointer text-left"
        )}
      >
        <div className="flex gap-0 sm:gap-0">
          <ActivityPhoto
            activity={activity}
            className="hidden h-auto w-28 sm:block sm:min-h-[7.5rem]"
          />
          <div className="min-w-0 flex-1 p-4">
            <ActivityPhoto
              activity={activity}
              className="mb-3 h-32 w-full rounded-lg sm:hidden"
            />
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
                className="rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide"
                style={{ background: badge.bg, color: badge.fg }}
              >
                {label}
                {activity.is_custom ? " · Custom" : ""}
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
        </div>
      </div>
    </>
  );

  return (
    <li className={cn("relative pb-6", isLast && "pb-0")}>
      {onSelect ? (
        <button type="button" className="block w-full" onClick={onSelect}>
          {content}
        </button>
      ) : (
        content
      )}
    </li>
  );
}
