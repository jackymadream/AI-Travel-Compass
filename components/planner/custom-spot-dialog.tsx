"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { geocodeNominatim, parseGoogleMapsUrl } from "@/lib/geo";
import type { ActivityCategory } from "@/lib/api";

export type CustomSpotPayload = {
  name: string;
  lat: number;
  lon: number;
  address?: string;
  description?: string;
  time_slot?: string;
  category?: ActivityCategory;
  duration_minutes?: number;
  cost_usd?: number;
};

type DraftFields = {
  name: string;
  description: string;
  time_slot: string;
  category: ActivityCategory;
  duration_minutes: string;
  cost_usd: string;
};

type CustomSpotDialogProps = {
  open: boolean;
  placingOnMap: boolean;
  cityHint?: string | null;
  initialCoords?: { lat: number; lon: number; address?: string } | null;
  /** Prefill visiting time (e.g. after the day's last stop). */
  defaultTimeSlot?: string | null;
  title?: string;
  /** `map` overlays the map; `modal` is a centered panel (timeline Add stop). */
  variant?: "map" | "modal";
  onClose: () => void;
  onStartMapPlace: () => void;
  onSubmit: (spot: CustomSpotPayload) => void;
};

const EMPTY_DRAFT: DraftFields = {
  name: "",
  description: "",
  time_slot: "15:00-16:00",
  category: "attraction",
  duration_minutes: "45",
  cost_usd: "0",
};

function toPayload(
  fields: DraftFields,
  lat: number,
  lon: number,
  address?: string
): CustomSpotPayload {
  const duration = Number.parseInt(fields.duration_minutes, 10);
  const cost = Number.parseFloat(fields.cost_usd);
  return {
    name: fields.name.trim() || "Custom spot",
    lat,
    lon,
    address,
    description: fields.description.trim() || undefined,
    time_slot: fields.time_slot.trim() || "15:00-16:00",
    category: fields.category,
    duration_minutes: Number.isFinite(duration) && duration > 0 ? duration : 45,
    cost_usd: Number.isFinite(cost) && cost >= 0 ? cost : 0,
  };
}

export function CustomSpotDialog({
  open,
  placingOnMap,
  cityHint,
  initialCoords,
  defaultTimeSlot = null,
  title = "Custom spot",
  variant = "map",
  onClose,
  onStartMapPlace,
  onSubmit,
}: CustomSpotDialogProps) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<DraftFields>(EMPTY_DRAFT);
  const [pendingCoords, setPendingCoords] = useState<{
    lat: number;
    lon: number;
    address?: string;
  } | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setError(null);
      setLoading(false);
      setDraft(EMPTY_DRAFT);
      setPendingCoords(null);
      return;
    }
    setDraft({
      ...EMPTY_DRAFT,
      time_slot: defaultTimeSlot?.trim() || EMPTY_DRAFT.time_slot,
    });
    if (initialCoords) {
      setPendingCoords({
        lat: initialCoords.lat,
        lon: initialCoords.lon,
        address: initialCoords.address || "Dropped on map",
      });
      setDraft((prev) =>
        prev.name.trim() ? prev : { ...prev, name: "Custom spot" }
      );
    }
  }, [open, initialCoords, defaultTimeSlot]);

  if (!open) return null;

  const canLookup = Boolean(query.trim() || draft.name.trim());

  async function handleResolve() {
    setError(null);
    setLoading(true);
    try {
      const lookup = query.trim() || draft.name.trim();
      const fromUrl = parseGoogleMapsUrl(lookup);
      if (fromUrl) {
        setPendingCoords({
          lat: fromUrl.lat,
          lon: fromUrl.lon,
          address: lookup.includes("http") ? "From Google Maps URL" : undefined,
        });
        if (!draft.name.trim()) {
          setDraft((prev) => ({ ...prev, name: "Custom spot" }));
        }
        return;
      }

      const geo = await geocodeNominatim(lookup, undefined, {
        name: draft.name,
        city: cityHint || undefined,
      });
      if (!geo) {
        setError("Could not find that place. Try a clearer name or a Maps URL.");
        return;
      }
      setPendingCoords({
        lat: geo.lat,
        lon: geo.lon,
        address: geo.label,
      });
      if (!draft.name.trim()) {
        setDraft((prev) => ({
          ...prev,
          name: geo.label.split(",")[0] || "Custom spot",
        }));
      }
    } catch {
      setError("Lookup failed. Check your network and try again.");
    } finally {
      setLoading(false);
    }
  }

  function handleAdd() {
    if (!pendingCoords) return;
    onSubmit(
      toPayload(draft, pendingCoords.lat, pendingCoords.lon, pendingCoords.address)
    );
    onClose();
  }

  return (
    <div
      className={
        variant === "modal"
          ? "relative z-[1100] max-h-[min(85vh,36rem)] w-full overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-xl"
          : "absolute left-3 top-3 z-[1100] max-h-[min(92%,28rem)] w-[min(100%-1.5rem,22rem)] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-lg"
      }
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
            {title}
          </p>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            {variant === "modal"
              ? "Add a name and confirm the place. You can skip extra fields and edit later."
              : "Add a name, then look up a place or click the map. You can skip extra fields and edit later."}
          </p>
        </div>
        <button
          type="button"
          className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      {placingOnMap && !pendingCoords ? (
        <p className="mt-3 rounded-lg bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--secondary-foreground)]">
          Click anywhere on the map to drop your waypoint…
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          <label className="block text-xs font-medium text-[var(--muted-foreground)]">
            Spot name
            <input
              value={draft.name}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, name: e.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
              placeholder="Shibuya Sky"
            />
          </label>
          {!pendingCoords ? (
            <>
              <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                Place or Maps URL
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
                  placeholder="Optional if the name is enough"
                />
              </label>
              {error ? (
                <p className="text-xs text-red-700" role="alert">
                  {error}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  type="button"
                  size="sm"
                  disabled={loading || !canLookup}
                  onClick={() => {
                    void handleResolve();
                  }}
                >
                  {loading ? "Looking up…" : "Add from text"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={onStartMapPlace}
                >
                  Click map to place
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-[var(--muted-foreground)]">
                Location ready
                {pendingCoords.address ? ` — ${pendingCoords.address}` : ""}. Fill
                details or keep defaults.
              </p>
              <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                Description
                <textarea
                  value={draft.description}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, description: e.target.value }))
                  }
                  rows={2}
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
                  placeholder="Optional notes"
                />
              </label>
              <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                Visiting time
                <input
                  value={draft.time_slot}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, time_slot: e.target.value }))
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
                  placeholder="15:00-16:00"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                  Category
                  <select
                    value={draft.category}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        category: e.target.value as ActivityCategory,
                      }))
                    }
                    className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                  >
                    <option value="attraction">Attraction</option>
                    <option value="food">Food</option>
                    <option value="rest">Rest</option>
                  </select>
                </label>
                <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                  Duration (min)
                  <input
                    value={draft.duration_minutes}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        duration_minutes: e.target.value,
                      }))
                    }
                    className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                  />
                </label>
              </div>
              <label className="block text-xs font-medium text-[var(--muted-foreground)]">
                Cost (USD)
                <input
                  value={draft.cost_usd}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, cost_usd: e.target.value }))
                  }
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
                />
              </label>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button type="button" size="sm" onClick={handleAdd}>
                  Add to itinerary
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setPendingCoords(null)}
                >
                  Back
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
