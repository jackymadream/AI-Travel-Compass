"use client";

import { ChevronDown, ChevronUp, MapPin, Plus, Timer } from "lucide-react";

import type { Activity, DailyItinerary } from "@/lib/api";
import { ActivityPhoto } from "@/components/planner/activity-photo";
import { Button } from "@/components/ui/button";
import type { ScheduleWarning } from "@/lib/itinerary-edit";
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
  editable?: boolean;
  warnings?: ScheduleWarning[];
  onMoveActivity?: (
    dayNumber: number,
    index: number,
    direction: -1 | 1
  ) => void;
  onAddStop?: (dayNumber: number) => void;
};

export function DayTimeline({
  days,
  selectedKey = null,
  onSelectActivity,
  editable = false,
  warnings = [],
  onMoveActivity,
  onAddStop,
}: DayTimelineProps) {
  return (
    <div className="space-y-8">
      {warnings.length > 0 ? (
        <div
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          role="status"
        >
          <p className="font-medium">Schedule notes</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {warnings.map((warning) => (
              <li key={`${warning.dayNumber}-${warning.message}`}>
                Day {warning.dayNumber}: {warning.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
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
                isLast={
                  activityIndex === day.activities.length - 1 && !onAddStop
                }
                selected={selectedKey === `${day.day_number}-${activityIndex}`}
                canMoveUp={editable && activityIndex > 0}
                canMoveDown={
                  editable && activityIndex < day.activities.length - 1
                }
                onMove={
                  onMoveActivity
                    ? (direction) =>
                        onMoveActivity(day.day_number, activityIndex, direction)
                    : undefined
                }
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
            {onAddStop ? (
              <li className="relative pb-0">
                <span
                  className="absolute -left-[1.9rem] top-3 h-3 w-3 rounded-full border-2 border-dashed border-[var(--primary)] bg-[var(--card)]"
                  aria-hidden
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-1 gap-1.5"
                  onClick={() => onAddStop(day.day_number)}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add stop
                </Button>
              </li>
            ) : null}
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
  canMoveUp,
  canMoveDown,
  onMove,
}: {
  activity: Activity;
  isLast: boolean;
  selected?: boolean;
  onSelect?: () => void;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onMove?: (direction: -1 | 1) => void;
}) {
  const badge = activityBadgeStyle(activity);
  const label = activity.is_food_slot
    ? activity.meal_role === "dinner"
      ? "Dinner"
      : "Lunch"
    : badge.label;
  const title = activity.display_name || activity.poi_name;

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
            className="hidden h-auto w-28 self-stretch sm:flex sm:min-h-[7.5rem]"
          />
          <div className="min-w-0 flex-1 p-4">
            <ActivityPhoto
              activity={activity}
              className="mb-3 flex h-32 w-full rounded-lg sm:hidden"
            />
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                  {activity.time_slot}
                </p>
                <h4 className="flex items-start gap-2 font-medium text-[var(--foreground)]">
                  <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary)]" />
                  <span>{title}</span>
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
      {onMove ? (
        <div className="absolute -left-[2.65rem] top-8 flex flex-col gap-0.5">
          <button
            type="button"
            className="rounded bg-[var(--card)] p-0.5 text-[var(--muted-foreground)] disabled:opacity-30"
            disabled={!canMoveUp}
            aria-label="Move stop earlier"
            onClick={(e) => {
              e.stopPropagation();
              onMove(-1);
            }}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="rounded bg-[var(--card)] p-0.5 text-[var(--muted-foreground)] disabled:opacity-30"
            disabled={!canMoveDown}
            aria-label="Move stop later"
            onClick={(e) => {
              e.stopPropagation();
              onMove(1);
            }}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : null}
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
