"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

import type { Activity, ActivityCategory } from "@/lib/api";
import { ActivityPhoto } from "@/components/planner/activity-photo";
import { Button } from "@/components/ui/button";
import { CATEGORY_OPTIONS } from "@/lib/itinerary-edit";

type PoiDetailDrawerProps = {
  activity: Activity | null;
  open: boolean;
  onClose: () => void;
  onSave?: (patch: Partial<Activity>) => void;
};

export function PoiDetailDrawer({
  activity,
  open,
  onClose,
  onSave,
}: PoiDetailDrawerProps) {
  const [draft, setDraft] = useState<Activity | null>(activity);

  useEffect(() => {
    setDraft(activity);
  }, [activity, open]);

  if (!open || !activity || !draft) return null;

  function save() {
    if (!onSave || !draft) return;
    onSave({
      poi_name: draft.poi_name,
      display_name: draft.display_name ?? draft.poi_name,
      description: draft.description,
      time_slot: draft.time_slot,
      duration_minutes: draft.duration_minutes,
      cost_usd: draft.cost_usd,
      category: draft.category,
      photo_url: draft.photo_url,
    });
    onClose();
  }

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
            {draft.display_name || draft.poi_name}
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
          key={draft.photo_url || draft.poi_name}
          activity={draft}
          className="mb-4 flex h-44 w-full rounded-xl"
        />

        {onSave ? (
          <div className="space-y-3 text-sm">
            <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Name
              <input
                value={draft.display_name || draft.poi_name}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    display_name: e.target.value,
                    poi_name: draft.is_custom ? e.target.value : draft.poi_name,
                  })
                }
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
              />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Description
              <textarea
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
                rows={3}
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Time
                <input
                  value={draft.time_slot}
                  onChange={(e) =>
                    setDraft({ ...draft, time_slot: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Category
                <select
                  value={draft.category}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      category: e.target.value as ActivityCategory,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                >
                  {CATEGORY_OPTIONS.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Duration (min)
                <input
                  type="number"
                  min={1}
                  value={draft.duration_minutes}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      duration_minutes: Number(e.target.value) || 1,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                Cost (USD)
                <input
                  type="number"
                  min={0}
                  value={draft.cost_usd}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      cost_usd: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                />
              </label>
            </div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              Image URL
              <input
                value={draft.photo_url || ""}
                onChange={(e) =>
                  setDraft({ ...draft, photo_url: e.target.value || null })
                }
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                placeholder="https://…"
              />
              {activity.is_food_slot ? (
                <span className="mt-1 block font-normal normal-case tracking-normal text-[var(--muted-foreground)]">
                  Optional. Leave blank to keep the lunch/dinner icon.
                </span>
              ) : null}
            </label>
            <Button type="button" className="w-full" onClick={save}>
              Save changes
            </Button>
          </div>
        ) : (
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
                <dd className="mt-0.5 text-[var(--foreground)]">
                  {activity.address}
                </dd>
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
        )}
      </div>
    </div>
  );
}
