"use client";

import { useEffect, useState } from "react";

import type { Activity } from "@/lib/api";
import { activityBadgeStyle } from "@/lib/planner-styles";
import { cn } from "@/lib/utils";

type ActivityPhotoProps = {
  activity: Activity;
  className?: string;
};

export function ActivityPhoto({ activity, className }: ActivityPhotoProps) {
  const [failed, setFailed] = useState(false);
  const badge = activityBadgeStyle(activity);
  const src = activity.photo_url;
  const showPlaceholder = !src || failed;

  useEffect(() => {
    setFailed(false);
  }, [src, activity.poi_name]);

  if (showPlaceholder) {
    return (
      <div
        className={cn("shrink-0", className)}
        style={{
          background: `linear-gradient(145deg, ${badge.bg}, ${badge.pin}33)`,
        }}
        aria-hidden
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      className={cn("shrink-0 object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}
