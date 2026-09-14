"use client";

import { useEffect, useState } from "react";
import {
  Landmark,
  MapPin,
  MoonStar,
  Trees,
  Utensils,
  type LucideIcon,
} from "lucide-react";

import type { Activity } from "@/lib/api";
import { activityBadgeStyle, CUSTOM_PIN } from "@/lib/planner-styles";
import { cn } from "@/lib/utils";

type ActivityPhotoProps = {
  activity: Activity;
  className?: string;
};

function CategoryIconPlaceholder({
  label,
  Icon,
  className,
  bg,
  fg,
}: {
  label: string;
  Icon: LucideIcon;
  className?: string;
  bg: string;
  fg: string;
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 flex-col items-center justify-center gap-1.5 self-stretch",
        className
      )}
      style={{ background: bg, color: fg }}
      aria-label={`${label} icon`}
    >
      <Icon className="h-8 w-8 opacity-90" strokeWidth={1.75} aria-hidden />
      <span className="text-[10px] font-semibold uppercase tracking-wide opacity-80">
        {label}
      </span>
    </div>
  );
}

export function ActivityPhoto({ activity, className }: ActivityPhotoProps) {
  const [failed, setFailed] = useState(false);
  const badge = activityBadgeStyle(activity);
  const src = activity.photo_url;
  const isCuisineMeal = Boolean(activity.is_food_slot);
  const showIcon = !src || failed;

  useEffect(() => {
    setFailed(false);
  }, [src, activity.poi_name, activity.meal_role, activity.category]);

  if (showIcon) {
    if (isCuisineMeal) {
      const isDinner = activity.meal_role === "dinner";
      return (
        <CategoryIconPlaceholder
          label={isDinner ? "Dinner" : "Lunch"}
          Icon={isDinner ? MoonStar : Utensils}
          className={className}
          bg={isDinner ? "#2c241c" : "#f3e0d4"}
          fg={isDinner ? "#f0dcc8" : "#7a3b16"}
        />
      );
    }

    if (activity.is_custom) {
      return (
        <CategoryIconPlaceholder
          label="Custom"
          Icon={MapPin}
          className={className}
          bg="#e8eef5"
          fg={CUSTOM_PIN}
        />
      );
    }

    const isRest = activity.category === "rest";
    return (
      <CategoryIconPlaceholder
        label={badge.label}
        Icon={isRest ? Trees : Landmark}
        className={className}
        bg={badge.bg}
        fg={badge.fg}
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src!}
      alt=""
      className={cn("shrink-0 object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}
