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

const CATEGORY_STOCK: Record<ActivityCategory, string> = {
  attraction:
    "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9?auto=format&fit=crop&w=800&q=80",
  food: "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=800&q=80",
  rest: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=800&q=80",
};

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
    photo_url: CATEGORY_STOCK[category],
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
    const tmp = next[fromIndex];
    next[fromIndex] = next[toIndex];
    next[toIndex] = tmp;
    return { ...day, activities: next, estimated_daily_cost: dayCost(next) };
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
