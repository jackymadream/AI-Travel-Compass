"use client";

import type { Activity } from "@/lib/api";
import { ActivityPhoto } from "@/components/planner/activity-photo";
import { X } from "lucide-react";

type PoiDetailDrawerProps = {
  activity: Activity | null;
  open: boolean;
  onClose: () => void;
};

export function PoiDetailDrawer({
  activity,
  open,
  onClose,
}: PoiDetailDrawerProps) {
  if (!open || !activity) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-[1200] flex w-full max-w-md flex-col border-l border-[var(--border)] bg-[var(--card)] shadow-xl"
      role="dialog"
      aria-modal="true"
      aria-label="POI details"
    >
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
            {activity.is_food_slot
              ? activity.meal_role === "dinner"
                ? "Dinner"
                : "Lunch"
              : activity.category}
            {activity.is_custom ? " · Custom" : null}
          </p>
          <h2 className="mt-1 font-[family-name:var(--font-display)] text-2xl leading-tight">
            {activity.poi_name}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full p-2 text-[var(--muted-foreground)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
          aria-label="Close details"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <ActivityPhoto
          activity={activity}
          className="mb-4 h-44 w-full rounded-xl"
        />

        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Category
            </dt>
            <dd className="mt-0.5 capitalize text-[var(--foreground)]">
              {activity.category}
              {activity.is_food_slot ? " (meal recommendation)" : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Description
            </dt>
            <dd className="mt-0.5 text-[var(--muted-foreground)]">
              {activity.description}
            </dd>
          </div>
          {activity.address ? (
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Address
              </dt>
              <dd className="mt-0.5 text-[var(--foreground)]">{activity.address}</dd>
            </div>
          ) : null}
          <div className="flex gap-4">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Duration
              </dt>
              <dd className="mt-0.5">{activity.duration_minutes} min</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Est. cost
              </dt>
              <dd className="mt-0.5">${activity.cost_usd.toFixed(0)}</dd>
            </div>
          </div>
        </dl>
      </div>
    </div>
  );
}
