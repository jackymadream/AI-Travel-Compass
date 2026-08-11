"use client";

import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  PLANNER_CITIES,
  type Locale,
  type TripPace,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const PACES: { value: TripPace; label: string; hint: string }[] = [
  { value: "relaxed", label: "Relaxed", hint: "Fewer stops, more buffer" },
  { value: "moderate", label: "Moderate", hint: "Balanced day" },
  { value: "packed", label: "Packed", hint: "More activities" },
];

const PREFERENCE_OPTIONS = [
  "food",
  "museum",
  "culture",
  "nightlife",
  "wellness",
  "urban",
] as const;

const LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "zh-HK", label: "繁" },
  { value: "ja", label: "日本語" },
];

export type PlannerControlsProps = {
  cityId: string;
  days: number;
  pace: TripPace;
  dailyBudget: number;
  preferences: string[];
  locale: Locale;
  loading: boolean;
  onCityIdChange: (value: string) => void;
  onDaysChange: (value: number) => void;
  onPaceChange: (value: TripPace) => void;
  onDailyBudgetChange: (value: number) => void;
  onPreferencesChange: (value: string[]) => void;
  onLocaleChange: (value: Locale) => void;
  onGenerate: () => void;
};

export function PlannerControls({
  cityId,
  days,
  pace,
  dailyBudget,
  preferences,
  locale,
  loading,
  onCityIdChange,
  onDaysChange,
  onPaceChange,
  onDailyBudgetChange,
  onPreferencesChange,
  onLocaleChange,
  onGenerate,
}: PlannerControlsProps) {
  function togglePreference(pref: string) {
    if (preferences.includes(pref)) {
      onPreferencesChange(preferences.filter((p) => p !== pref));
    } else {
      onPreferencesChange([...preferences, pref]);
    }
  }

  return (
    <aside className="flex h-fit flex-col gap-7 rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 p-6 shadow-sm backdrop-blur-sm lg:sticky lg:top-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          Controls
        </p>
        <h2 className="mt-2 font-[family-name:var(--font-display)] text-2xl text-[var(--foreground)]">
          Plan the trip
        </h2>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          The agent retrieves POIs, then validates budget and pace.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="planner-city">City</Label>
        <Select value={cityId} onValueChange={onCityIdChange}>
          <SelectTrigger id="planner-city" aria-label="City">
            <SelectValue placeholder="Select city" />
          </SelectTrigger>
          <SelectContent>
            {PLANNER_CITIES.map((city) => (
              <SelectItem key={city.id} value={city.id}>
                {city.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <Label htmlFor="planner-days">Days</Label>
          <span className="font-[family-name:var(--font-display)] text-lg text-[var(--primary)]">
            {days}
          </span>
        </div>
        <Slider
          id="planner-days"
          min={1}
          max={7}
          step={1}
          value={[days]}
          onValueChange={(value) => onDaysChange(value[0] ?? 1)}
          aria-label="Number of days"
        />
        <div className="flex justify-between text-xs text-[var(--muted-foreground)]">
          <span>1</span>
          <span>7</span>
        </div>
      </div>

      <div className="space-y-2">
        <Label>Pace</Label>
        <div className="grid gap-2">
          {PACES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onPaceChange(option.value)}
              className={cn(
                "rounded-xl border px-3 py-2.5 text-left transition-colors",
                pace === option.value
                  ? "border-[var(--primary)] bg-[var(--secondary)]"
                  : "border-[var(--border)] bg-[var(--background)] hover:border-[var(--primary)]"
              )}
            >
              <span className="block text-sm font-medium">{option.label}</span>
              <span className="text-xs text-[var(--muted-foreground)]">
                {option.hint}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <Label htmlFor="planner-budget">Daily budget</Label>
          <span className="font-[family-name:var(--font-display)] text-lg text-[var(--primary)]">
            ${dailyBudget}
            <span className="text-sm text-[var(--muted-foreground)]">/day</span>
          </span>
        </div>
        <Slider
          id="planner-budget"
          min={20}
          max={300}
          step={5}
          value={[dailyBudget]}
          onValueChange={(value) => onDailyBudgetChange(value[0] ?? 20)}
          aria-label="Daily budget in USD"
        />
        <div className="flex justify-between text-xs text-[var(--muted-foreground)]">
          <span>$20</span>
          <span>$300</span>
        </div>
      </div>

      <div className="space-y-2">
        <Label>Preferences</Label>
        <div className="flex flex-wrap gap-2">
          {PREFERENCE_OPTIONS.map((pref) => {
            const active = preferences.includes(pref);
            return (
              <button
                key={pref}
                type="button"
                onClick={() => togglePreference(pref)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs capitalize transition-colors",
                  active
                    ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:border-[var(--primary)] hover:text-[var(--primary)]"
                )}
              >
                {pref}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <Label>Locale</Label>
        <div className="flex gap-2">
          {LOCALES.map((item) => (
            <Button
              key={item.value}
              type="button"
              size="sm"
              variant={locale === item.value ? "default" : "outline"}
              onClick={() => onLocaleChange(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </div>

      <Button
        type="button"
        className="h-12 w-full"
        disabled={loading}
        onClick={onGenerate}
      >
        {loading ? "Planning…" : "Generate itinerary"}
      </Button>
    </aside>
  );
}
