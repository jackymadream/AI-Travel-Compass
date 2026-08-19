"use client";

import { getApiBaseUrl } from "@/lib/api";

/** Parse lat/lon from common Google Maps URL shapes (no Google API). */
export function parseGoogleMapsUrl(
  input: string
): { lat: number; lon: number; label?: string } | null {
  const text = input.trim();
  if (!text) return null;

  const at = text.match(/@(-?\d+\.?\d*),(-?\d+\.?\d*)/);
  if (at) {
    return { lat: Number(at[1]), lon: Number(at[2]) };
  }

  const bang3d = text.match(/!3d(-?\d+\.?\d*)!4d(-?\d+\.?\d*)/);
  if (bang3d) {
    return { lat: Number(bang3d[1]), lon: Number(bang3d[2]) };
  }

  const ll = text.match(/[?&](?:ll|center)=(-?\d+\.?\d*),(-?\d+\.?\d*)/i);
  if (ll) {
    return { lat: Number(ll[1]), lon: Number(ll[2]) };
  }

  const q = text.match(/[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)/i);
  if (q) {
    return { lat: Number(q[1]), lon: Number(q[2]) };
  }

  const destination = text.match(
    /[?&]destination=(-?\d+\.?\d*),(-?\d+\.?\d*)/i
  );
  if (destination) {
    return { lat: Number(destination[1]), lon: Number(destination[2]) };
  }

  return null;
}

export async function geocodeNominatim(
  query: string,
  signal?: AbortSignal,
  extras?: { name?: string; city?: string }
): Promise<{ lat: number; lon: number; label: string } | null> {
  const q = query.trim();
  const name = extras?.name?.trim() || "";
  if (!q && !name) return null;

  const parsed = parseGoogleMapsUrl(q);
  if (parsed) {
    return { lat: parsed.lat, lon: parsed.lon, label: name || q };
  }

  const res = await fetch(`${getApiBaseUrl()}/api/v1/geocode`, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: q || name,
      name: name || undefined,
      city: extras?.city || undefined,
    }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as {
    ok?: boolean;
    lat?: number;
    lon?: number;
    label?: string;
  };
  if (!data.ok || data.lat == null || data.lon == null) return null;
  return {
    lat: Number(data.lat),
    lon: Number(data.lon),
    label: data.label || name || q,
  };
}
