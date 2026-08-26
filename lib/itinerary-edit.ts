import type { Activity, ActivityCategory, DailyItinerary } from "@/lib/api";
import type { CustomSpotPayload } from "@/components/planner/custom-spot-dialog";

export type ScheduleWarning = {
  dayNumber: number;
  message: string;
};

export function slotStartMinutes(slot: string): number {
  const start = (slot || "").split("-", 1)[0].trim();
  if (!start.includes(":")) return 24 * 60;
  const [hh, mm] = start.split(":", 2);
  const hours = Number.parseInt(hh, 10);
  const minutes = Number.parseInt(mm, 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return 24 * 60;
  return hours * 60 + minutes;
}

export function slotEndMinutes(slot: string): number {
  const parts = (slot || "").split("-");
  if (parts.length >= 2) {
    const end = slotStartMinutes(parts[1].trim());
    if (end < 24 * 60) return end;
  }
  return slotStartMinutes(slot) + 60;
}

export function formatMinutes(totalMinutes: number): string {
  const clamped = Math.max(0, Math.min(24 * 60 - 1, Math.round(totalMinutes)));
  const hours = Math.floor(clamped / 60);
  const minutes = clamped % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

/** Re-pack time slots in list order from ``dayStartMin`` using each stop's duration. */
export function packActivityTimes(
  activities: Activity[],
  dayStartMin?: number
): Activity[] {
  if (activities.length === 0) return activities;
  const starts = activities
    .map((a) => slotStartMinutes(a.time_slot))
    .filter((m) => m < 24 * 60);
  let cursor =
    dayStartMin ??
    (starts.length ? Math.min(...starts) : 9 * 60);
  if (!Number.isFinite(cursor) || cursor >= 24 * 60) cursor = 9 * 60;
  return activities.map((act) => {
    const dur = Math.max(1, act.duration_minutes || 60);
    const start = cursor;
    const end = Math.min(start + dur, 24 * 60 - 1);
    cursor = end;
    return {
      ...act,
      time_slot: `${formatMinutes(start)}-${formatMinutes(end)}`,
    };
  });
}

export function suggestedSlotAfterLast(
  activities: Activity[],
  durationMinutes = 45
): string {
  const last = activities[activities.length - 1];
  const start = last ? slotEndMinutes(last.time_slot) : 15 * 60;
  const end = Math.min(start + Math.max(1, durationMinutes), 24 * 60 - 1);
  return `${formatMinutes(start)}-${formatMinutes(end)}`;
}

export function sortActivities(activities: Activity[]): Activity[] {
  return [...activities].sort(
    (a, b) => slotStartMinutes(a.time_slot) - slotStartMinutes(b.time_slot)
  );
}

export function overlappingPairs(activities: Activity[]): [string, string][] {
  const ranges = activities
    .map((act) => {
      const parts = (act.time_slot || "").split("-");
      if (parts.length < 2) return null;
      const start = slotStartMinutes(parts[0]);
      const end = slotStartMinutes(parts[1]);
      if (start >= 24 * 60 || end >= 24 * 60) return null;
      return { start, end, name: act.poi_name };
    })
    .filter((row): row is { start: number; end: number; name: string } => Boolean(row));

  const hits: [string, string][] = [];
  for (let i = 0; i < ranges.length; i += 1) {
    for (let j = i + 1; j < ranges.length; j += 1) {
      const a = ranges[i];
      const b = ranges[j];
      if (a.start < b.end && b.start < a.end) {
        hits.push([a.name, b.name]);
      }
    }
  }
  return hits;
}

export function dayCost(activities: Activity[]): number {
  return activities.reduce((sum, act) => sum + (act.cost_usd || 0), 0);
}

export function scheduleWarnings(
  days: DailyItinerary[],
  dailyBudgetUsd?: number
): ScheduleWarning[] {
  const warnings: ScheduleWarning[] = [];
  for (const day of days) {
    const overlaps = overlappingPairs(day.activities);
    if (overlaps.length) {
      warnings.push({
        dayNumber: day.day_number,
        message: `Overlapping times: ${overlaps
          .slice(0, 2)
          .map(([a, b]) => `${a} / ${b}`)
          .join("; ")}`,
      });
    }
    for (const note of day.warnings || []) {
      warnings.push({
        dayNumber: day.day_number,
        message: note,
      });
    }
    const cost = dayCost(day.activities);
    if (dailyBudgetUsd != null && cost > dailyBudgetUsd) {
      warnings.push({
        dayNumber: day.day_number,
        message: `Day ${day.day_number} is over budget by $${(cost - dailyBudgetUsd).toFixed(0)}`,
      });
    }
  }
  return warnings;
}

export function activityFromCustomSpot(spot: CustomSpotPayload): Activity {
  const category = spot.category || "attraction";
  return {
    time_slot: spot.time_slot || "15:00-16:00",
    poi_name: spot.name,
    category,
    cost_usd: spot.cost_usd ?? 0,
    duration_minutes: spot.duration_minutes ?? 45,
    description:
      spot.description ||
      (spot.address
        ? `Custom waypoint — ${spot.address}`
        : "Custom waypoint added on the map."),
    lat: spot.lat,
    lon: spot.lon,
    address: spot.address ?? null,
    is_custom: true,
    is_food_slot: false,
    meal_role: null,
    photo_url: null,
    display_name: spot.name,
  };
}

export function insertCustomSpot(
  days: DailyItinerary[],
  dayNumber: number,
  spot: CustomSpotPayload
): DailyItinerary[] {
  return days.map((day) => {
    if (day.day_number !== dayNumber) return day;
    const activities = sortActivities([
      ...day.activities,
      activityFromCustomSpot(spot),
    ]);
    return {
      ...day,
      activities,
      estimated_daily_cost: dayCost(activities),
    };
  });
}

/** Append a custom stop after the last stop of the day (does not re-sort by time). */
export function appendCustomSpot(
  days: DailyItinerary[],
  dayNumber: number,
  spot: CustomSpotPayload
): DailyItinerary[] {
  return days.map((day) => {
    if (day.day_number !== dayNumber) return day;
    const duration = spot.duration_minutes ?? 45;
    const time_slot =
      spot.time_slot?.trim() ||
      suggestedSlotAfterLast(day.activities, duration);
    const activities = [
      ...day.activities,
      activityFromCustomSpot({ ...spot, time_slot, duration_minutes: duration }),
    ];
    return {
      ...day,
      activities,
      estimated_daily_cost: dayCost(activities),
    };
  });
}

export function moveActivity(
  days: DailyItinerary[],
  dayNumber: number,
  fromIndex: number,
  direction: -1 | 1
): DailyItinerary[] {
  return days.map((day) => {
    if (day.day_number !== dayNumber) return day;
    const next = [...day.activities];
    const toIndex = fromIndex + direction;
    if (toIndex < 0 || toIndex >= next.length) return day;
    const dayStart = Math.min(
      ...day.activities.map((a) => slotStartMinutes(a.time_slot))
    );
    const tmp = next[fromIndex];
    next[fromIndex] = next[toIndex];
    next[toIndex] = tmp;
    const activities = packActivityTimes(next, dayStart);
    return {
      ...day,
      activities,
      estimated_daily_cost: dayCost(activities),
    };
  });
}

export function updateActivity(
  days: DailyItinerary[],
  dayNumber: number,
  index: number,
  patch: Partial<Activity>
): DailyItinerary[] {
  return days.map((day) => {
    if (day.day_number !== dayNumber) return day;
    const next = day.activities.map((act, i) =>
      i === index ? { ...act, ...patch } : act
    );
    const activities = sortActivities(next);
    return {
      ...day,
      activities,
      estimated_daily_cost: dayCost(activities),
    };
  });
}

export function tripTotal(days: DailyItinerary[]): number {
  return days.reduce((sum, day) => sum + dayCost(day.activities), 0);
}

export const CATEGORY_OPTIONS: ActivityCategory[] = [
  "attraction",
  "food",
  "rest",
];

/** Clear auto-seeded cuisine photos so the UI uses lunch/dinner icons by default. */
export function clearCuisineMealPhotos(
  days: DailyItinerary[]
): DailyItinerary[] {
  return days.map((day) => ({
    ...day,
    activities: day.activities.map((act) =>
      act.is_food_slot ? { ...act, photo_url: null } : act
    ),
  }));
}