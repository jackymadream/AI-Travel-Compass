"use client";

import { useMemo, useState } from "react";

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
  type CitySummary,
  type Country,
  type Locale,
  type TripPace,
} from "@/lib/api";
import {
  PRIMARY_PREFERENCE_CHIPS,
  discoveryModeOf,
  filterTaxonomyTags,
  parseFreeTextPreferences,
  withDiscoveryMode,
} from "@/lib/planner-preferences";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";

const PACES: { value: TripPace; label: string; hint: string }[] = [
  { value: "relaxed", label: "Relaxed", hint: "Fewer stops, more buffer" },
  { value: "moderate", label: "Moderate", hint: "Balanced day" },
  { value: "packed", label: "Packed", hint: "More activities" },
];

const LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "zh-HK", label: "繁" },
  { value: "ja", label: "日本語" },
];

/** Sentinel value for “Any city in country” — parent resolves to first city. */
export const ANY_CITY_VALUE = "__any__";

export type PlannerControlsProps = {
  countryId: string;
  cityId: string;
  countries?: Country[];
  cities?: CitySummary[];
  days: number;
  pace: TripPace;
  dailyBudget: number;
  preferences: string[];
  locale: Locale;
  loading: boolean;
  onCountryIdChange: (value: string) => void;
  onCityIdChange: (value: string) => void;
  onDaysChange: (value: number) => void;
  onPaceChange: (value: TripPace) => void;
  onDailyBudgetChange: (value: number) => void;
  onPreferencesChange: (value: string[]) => void;
  onLocaleChange: (value: Locale) => void;
  onGenerate: () => void;
};

export function PlannerControls({
  countryId,
  cityId,
  countries,
  cities,
  days,
  pace,
  dailyBudget,
  preferences,
  locale,
  loading,
  onCountryIdChange,
  onCityIdChange,
  onDaysChange,
  onPaceChange,
  onDailyBudgetChange,
  onPreferencesChange,
  onLocaleChange,
  onGenerate,
}: PlannerControlsProps) {
  const t = useTranslations("planner");
  const [tagSearch, setTagSearch] = useState("");
  const [freeText, setFreeText] = useState("");

  const cityOptions =
    cities && cities.length > 0
      ? cities
      : PLANNER_CITIES.map((c) => ({
          id: c.id,
          slug: c.name.toLowerCase(),
          name: c.name,
          country_id: null as string | null,
          country_iso: null as string | null,
        }));

  const countryOptions = useMemo(() => {
    if (countries && countries.length > 0) {
      return [...countries].sort((a, b) => a.name.localeCompare(b.name));
    }
    const seen = new Map<string, { id: string; name: string; iso: string }>();
    for (const city of cityOptions) {
      const id = city.country_id;
      const iso = city.country_iso;
      if (!id || !iso || seen.has(id)) continue;
      seen.set(id, { id, name: iso, iso });
    }
    return Array.from(seen.values()).map((c) => ({
      id: c.id,
      name: c.name,
      iso_code: c.iso,
    }));
  }, [countries, cityOptions]);

  const citiesInCountry = useMemo(() => {
    if (!countryId) return cityOptions;
    return cityOptions.filter((c) => c.country_id === countryId);
  }, [cityOptions, countryId]);

  const selectedCountryName =
    countryOptions.find((c) => c.id === countryId)?.name ?? "this country";

  const citySelectValue =
    cityId && citiesInCountry.some((c) => c.id === cityId) ? cityId : "";

  const searchHits = useMemo(() => filterTaxonomyTags(tagSearch), [tagSearch]);

  const extraSelected = preferences.filter(
    (p) =>
      !(PRIMARY_PREFERENCE_CHIPS as readonly string[]).includes(p) &&
      p !== "popular" &&
      p !== "unconventional"
  );
  const discovery = discoveryModeOf(preferences);

  function togglePreference(pref: string) {
    if (preferences.includes(pref)) {
      onPreferencesChange(preferences.filter((p) => p !== pref));
    } else {
      onPreferencesChange([...preferences, pref]);
    }
  }

  function addPreferences(tokens: string[]) {
    if (!tokens.length) return;
    const next = [...preferences];
    for (const t of tokens) {
      if (!next.includes(t)) next.push(t);
    }
    onPreferencesChange(next);
  }

  function handleCountryChange(nextCountryId: string) {
    onCountryIdChange(nextCountryId);
    const inCountry = cityOptions
      .filter((c) => c.country_id === nextCountryId)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (inCountry[0]) {
      onCityIdChange(inCountry[0].id);
    }
  }

  function handleCityChange(value: string) {
    if (value === ANY_CITY_VALUE) {
      const sorted = [...citiesInCountry].sort((a, b) =>
        a.name.localeCompare(b.name)
      );
      if (sorted[0]) onCityIdChange(sorted[0].id);
      return;
    }
    onCityIdChange(value);
  }

  return (
    <aside className="flex h-fit flex-col gap-7 rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 p-6 shadow-sm backdrop-blur-sm lg:sticky lg:top-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          {t("controls")}
        </p>
        <h2 className="mt-2 font-[family-name:var(--font-display)] text-2xl text-[var(--foreground)]">
          {t("planTrip")}
        </h2>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          {t("agentHint")}
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="planner-country">Country</Label>
        <Select value={countryId || undefined} onValueChange={handleCountryChange}>
          <SelectTrigger id="planner-country" aria-label="Country">
            <SelectValue placeholder="Select country" />
          </SelectTrigger>
          <SelectContent>
            {countryOptions.map((country) => (
              <SelectItem key={country.id} value={country.id}>
                {"iso_code" in country && country.iso_code
                  ? `${country.name} (${country.iso_code})`
                  : country.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="planner-city">City</Label>
        <Select
          value={citySelectValue || undefined}
          onValueChange={handleCityChange}
          disabled={!countryId && citiesInCountry.length === 0}
        >
          <SelectTrigger id="planner-city" aria-label="City">
            <SelectValue placeholder="Select city" />
          </SelectTrigger>
          <SelectContent>
            {countryId && citiesInCountry.length > 0 ? (
              <SelectItem value={ANY_CITY_VALUE}>
                Any city in {selectedCountryName}
              </SelectItem>
            ) : null}
            {citiesInCountry.map((city) => (
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
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() =>
              onPreferencesChange(withDiscoveryMode(preferences, "popular"))
            }
            className={cn(
              "rounded-xl border px-3 py-2 text-left text-xs transition-colors",
              discovery === "popular"
                ? "border-[var(--primary)] bg-[var(--secondary)]"
                : "border-[var(--border)] bg-[var(--background)]"
            )}
          >
            <span className="block font-medium">Popular landmarks</span>
            <span className="text-[var(--muted-foreground)]">Default mix</span>
          </button>
          <button
            type="button"
            onClick={() =>
              onPreferencesChange(
                withDiscoveryMode(preferences, "unconventional")
              )
            }
            className={cn(
              "rounded-xl border px-3 py-2 text-left text-xs transition-colors",
              discovery === "unconventional"
                ? "border-[var(--primary)] bg-[var(--secondary)]"
                : "border-[var(--border)] bg-[var(--background)]"
            )}
          >
            <span className="block font-medium">Unconventional</span>
            <span className="text-[var(--muted-foreground)]">Lesser-known</span>
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {PRIMARY_PREFERENCE_CHIPS.map((pref) => {
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
                {pref.replace(/-/g, " ")}
              </button>
            );
          })}
          {extraSelected.map((pref) => (
            <button
              key={pref}
              type="button"
              onClick={() => togglePreference(pref)}
              className="rounded-full border border-[var(--primary)] bg-[var(--primary)] px-3 py-1.5 text-xs capitalize text-[var(--primary-foreground)]"
            >
              {pref.replace(/-/g, " ")} ×
            </button>
          ))}
        </div>

        <div className="space-y-1.5 pt-1">
          <Label
            htmlFor="pref-search"
            className="text-xs text-[var(--muted-foreground)]"
          >
            Search interests
          </Label>
          <input
            id="pref-search"
            value={tagSearch}
            onChange={(e) => setTagSearch(e.target.value)}
            placeholder="e.g. anime, onsen, hiking…"
            className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
          />
          {searchHits.length > 0 ? (
            <ul className="max-h-36 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--background)] text-sm">
              {searchHits.map((tag) => (
                <li key={tag}>
                  <button
                    type="button"
                    className="w-full px-3 py-1.5 text-left capitalize hover:bg-[var(--secondary)]"
                    onClick={() => {
                      addPreferences([tag]);
                      setTagSearch("");
                    }}
                  >
                    {tag.replace(/-/g, " ")}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label
            htmlFor="pref-free"
            className="text-xs text-[var(--muted-foreground)]"
          >
            Other requirements
          </Label>
          <div className="flex gap-2">
            <input
              id="pref-free"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addPreferences(parseFreeTextPreferences(freeText));
                  setFreeText("");
                }
              }}
              placeholder="quiet gardens, kid-friendly…"
              className="min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                addPreferences(parseFreeTextPreferences(freeText));
                setFreeText("");
              }}
            >
              Add
            </Button>
          </div>
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
        {loading ? t("planning") : t("generate")}
      </Button>
    </aside>
  );
}
