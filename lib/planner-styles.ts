import type { Activity, ActivityCategory } from "@/lib/api";

export type CategoryStyle = {
  label: string;
  bg: string;
  fg: string;
  pin: string;
};

export const CATEGORY_STYLES: Record<ActivityCategory, CategoryStyle> = {
  attraction: {
    label: "Attraction",
    bg: "#d7ebe4",
    fg: "#1a3a33",
    pin: "#1a6b5c",
  },
  food: {
    label: "Food",
    bg: "#f3e0d4",
    fg: "#7a3b16",
    pin: "#c45c26",
  },
  rest: {
    label: "Rest",
    bg: "#e4e8f0",
    fg: "#334155",
    pin: "#475569",
  },
};

export const CUSTOM_PIN = "#64748b";

export function activityPinColor(activity: Activity): string {
  if (activity.is_custom) return CUSTOM_PIN;
  if (activity.is_food_slot) return CATEGORY_STYLES.food.pin;
  return CATEGORY_STYLES[activity.category]?.pin ?? CATEGORY_STYLES.attraction.pin;
}

export function activityBadgeStyle(activity: Activity): CategoryStyle {
  if (activity.is_food_slot) return CATEGORY_STYLES.food;
  return CATEGORY_STYLES[activity.category] ?? CATEGORY_STYLES.attraction;
}
