"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { geocodeNominatim, parseGoogleMapsUrl } from "@/lib/geo";

export type CustomSpotPayload = {
  name: string;
  lat: number;
  lon: number;
  address?: string;
};

type CustomSpotDialogProps = {
  open: boolean;
  placingOnMap: boolean;
  onClose: () => void;
  onStartMapPlace: () => void;
  onSubmit: (spot: CustomSpotPayload) => void;
};

export function CustomSpotDialog({
  open,
  placingOnMap,
  onClose,
  onStartMapPlace,
  onSubmit,
}: CustomSpotDialogProps) {
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  async function handleResolve() {
    setError(null);
    setLoading(true);
    try {
      const fromUrl = parseGoogleMapsUrl(query);
      if (fromUrl) {
        onSubmit({
          name: name.trim() || "Custom spot",
          lat: fromUrl.lat,
          lon: fromUrl.lon,
          address: query.includes("http") ? "From Google Maps URL" : undefined,
        });
        setName("");
        setQuery("");
        onClose();
        return;
      }

      const geo = await geocodeNominatim(query);
      if (!geo) {
        setError("Could not find that place. Try a clearer name or a Maps URL.");
        return;
      }
      onSubmit({
        name: name.trim() || geo.label.split(",")[0] || "Custom spot",
        lat: geo.lat,
        lon: geo.lon,
        address: geo.label,
      });
      setName("");
      setQuery("");
      onClose();
    } catch {
      setError("Lookup failed. Check your network and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="absolute left-3 top-3 z-[1100] w-[min(100%-1.5rem,22rem)] rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
            Custom spot
          </p>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            Click the map, paste a Google Maps URL, or type a place name.
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

      {placingOnMap ? (
        <p className="mt-3 rounded-lg bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--secondary-foreground)]">
          Click anywhere on the map to drop your waypoint…
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          <label className="block text-xs font-medium text-[var(--muted-foreground)]">
            Spot name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
              placeholder="Optional label"
            />
          </label>
          <label className="block text-xs font-medium text-[var(--muted-foreground)]">
            Place or Maps URL
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)]"
              placeholder="Shibuya Crossing or https://maps.google.com/…"
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
              disabled={loading || !query.trim()}
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
        </div>
      )}
    </div>
  );
}
