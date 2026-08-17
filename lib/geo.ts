"use client";

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
  signal?: AbortSignal
): Promise<{ lat: number; lon: number; label: string } | null> {
  const q = query.trim();
  if (!q) return null;

  const url = new URL("https://nominatim.openstreetmap.org/search");
  url.searchParams.set("format", "json");
  url.searchParams.set("limit", "1");
  url.searchParams.set("q", q);

  const res = await fetch(url.toString(), {
    signal,
    headers: {
      Accept: "application/json",
    },
  });
  if (!res.ok) return null;
  const data = (await res.json()) as Array<{
    lat: string;
    lon: string;
    display_name?: string;
  }>;
  const hit = data[0];
  if (!hit) return null;
  return {
    lat: Number(hit.lat),
    lon: Number(hit.lon),
    label: hit.display_name || q,
  };
}
