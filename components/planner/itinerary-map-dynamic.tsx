"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const ItineraryMapInner = dynamic(
  () =>
    import("@/components/planner/itinerary-map").then((m) => m.ItineraryMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[360px] items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--card)] text-sm text-[var(--muted-foreground)] md:h-[440px]">
        Loading map…
      </div>
    ),
  }
);

export function ItineraryMapDynamic(
  props: ComponentProps<typeof ItineraryMapInner>
) {
  return <ItineraryMapInner {...props} />;
}
