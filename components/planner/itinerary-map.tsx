"use client";

import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  CustomSpotDialog,
  type CustomSpotPayload,
} from "@/components/planner/custom-spot-dialog";
import { Button } from "@/components/ui/button";
import type { Activity, DailyItinerary } from "@/lib/api";
import { activityPinColor } from "@/lib/planner-styles";

type MappedActivity = Activity & { dayNumber: number; activityIndex: number };

type ItineraryMapProps = {
  days: DailyItinerary[];
  selectedDay: number;
  onSelectedDayChange: (day: number) => void;
  selectedKey: string | null;
  onSelectActivity: (
    activity: Activity,
    dayNumber: number,
    index: number
  ) => void;
  onAddCustomSpot: (dayNumber: number, spot: CustomSpotPayload) => void;
  cityCenter?: { lat: number; lon: number } | null;
};

function numberedIcon(order: number, color: string, selected: boolean) {
  const size = selected ? 34 : 28;
  return L.divIcon({
    className: "tc-map-pin",
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:9999px;
      background:${color};color:#fff;font-weight:700;font-size:13px;
      display:flex;align-items:center;justify-content:center;
      border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);
      ">${order}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 13);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [36, 36] });
  }, [map, points]);
  return null;
}

function MapClickCapture({
  enabled,
  onClick,
}: {
  enabled: boolean;
  onClick: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(e) {
      if (!enabled) return;
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export function ItineraryMap({
  days,
  selectedDay,
  onSelectedDayChange,
  selectedKey,
  onSelectActivity,
  onAddCustomSpot,
  cityCenter,
}: ItineraryMapProps) {
  const [showMeals, setShowMeals] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [placingOnMap, setPlacingOnMap] = useState(false);

  const dayPlan = days.find((d) => d.day_number === selectedDay) ?? days[0];

  const mapped = useMemo(() => {
    const acts: MappedActivity[] = [];
    if (!dayPlan) return acts;
    dayPlan.activities.forEach((activity, activityIndex) => {
      acts.push({
        ...activity,
        dayNumber: dayPlan.day_number,
        activityIndex,
      });
    });
    return acts;
  }, [dayPlan]);

  const visible = useMemo(
    () =>
      mapped.filter((a) => {
        if (a.lat == null || a.lon == null) return false;
        if (a.is_food_slot && !showMeals) return false;
        return true;
      }),
    [mapped, showMeals]
  );

  const points = useMemo(
    () =>
      visible.map(
        (a) => [a.lat as number, a.lon as number] as [number, number]
      ),
    [visible]
  );

  const fallbackCenter: [number, number] = cityCenter
    ? [cityCenter.lat, cityCenter.lon]
    : (points[0] ?? [35.68, 139.76]);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {days.map((d) => (
            <button
              key={d.day_number}
              type="button"
              onClick={() => onSelectedDayChange(d.day_number)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                d.day_number === selectedDay
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)]"
              }`}
            >
              Day {d.day_number}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
            <input
              type="checkbox"
              checked={showMeals}
              onChange={(e) => setShowMeals(e.target.checked)}
            />
            Show meals
          </label>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => {
              setCustomOpen(true);
              setPlacingOnMap(false);
            }}
          >
            Custom Spot
          </Button>
        </div>
      </div>

      <div className="relative h-[360px] w-full md:h-[440px]">
        <MapContainer
          center={fallbackCenter}
          zoom={12}
          className="h-full w-full"
          scrollWheelZoom
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitBounds points={points.length ? points : [fallbackCenter]} />
          <MapClickCapture
            enabled={placingOnMap}
            onClick={(lat, lon) => {
              onAddCustomSpot(selectedDay, {
                name: "Custom spot",
                lat,
                lon,
              });
              setPlacingOnMap(false);
              setCustomOpen(false);
            }}
          />
          {visible.map((activity, orderIdx) => {
            const key = `${activity.dayNumber}-${activity.activityIndex}`;
            const color = activityPinColor(activity);
            return (
              <Marker
                key={key}
                position={[activity.lat as number, activity.lon as number]}
                icon={numberedIcon(orderIdx + 1, color, selectedKey === key)}
                eventHandlers={{
                  click: () =>
                    onSelectActivity(
                      activity,
                      activity.dayNumber,
                      activity.activityIndex
                    ),
                }}
              />
            );
          })}
        </MapContainer>

        <CustomSpotDialog
          open={customOpen}
          placingOnMap={placingOnMap}
          onClose={() => {
            setCustomOpen(false);
            setPlacingOnMap(false);
          }}
          onStartMapPlace={() => setPlacingOnMap(true)}
          onSubmit={(spot) => {
            onAddCustomSpot(selectedDay, spot);
          }}
        />
      </div>

      {visible.length === 0 ? (
        <p className="border-t border-[var(--border)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
          No mappable stops for this day yet
          {!showMeals ? " (meal slots are hidden by default)" : ""}. Add a
          Custom Spot or pick another day.
        </p>
      ) : null}
    </div>
  );
}
