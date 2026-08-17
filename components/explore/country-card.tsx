"use client";

import Link from "next/link";
import { Calendar, MapPin, Shield, Sparkles, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { type Country, type SearchHit } from "@/lib/api";
import { cn } from "@/lib/utils";

type CountryBrowseCardProps = {
  index: number;
  country: Country;
  expanded: boolean;
  muted?: boolean;
  /** AI search match 0–100; omit for filter browse. */
  matchPercentValue?: number;
  /** Soft-matched interest tags from AI search (shown preferentially). */
  highlightTags?: string[];
  resolveCityId: (countryId: string, citySlug: string) => string | null;
  onToggle: () => void;
};

export function CountryBrowseCard({
  index,
  country,
  expanded,
  muted = false,
  matchPercentValue,
  highlightTags,
  resolveCityId,
  onToggle,
}: CountryBrowseCardProps) {
  const tags =
    (country.tags && country.tags.length > 0
      ? country.tags
      : country.region_tags) ?? [];
  const season =
    country.best_season || country.best_travel_season?.label || "";
  const interestChips = (highlightTags ?? []).filter(Boolean).slice(0, 4);
  const collapsedTags =
    interestChips.length > 0 ? interestChips : tags.slice(0, 3);
  const topCities = country.top_cities ?? [];
  const photo = country.photo_url;

  return (
    <article
      className={cn(
        "animate-fade-up group relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-sm transition-all duration-300",
        expanded
          ? "sm:col-span-2 xl:col-span-3"
          : "hover:-translate-y-0.5",
        muted && !expanded && "opacity-55"
      )}
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      >
        <div
          className={cn(
            "relative overflow-hidden",
            expanded ? "min-h-[220px]" : "min-h-[200px]"
          )}
        >
          {photo ? (
            <img
              key={photo}
              src={photo}
              alt=""
              className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-[var(--secondary)] to-[var(--muted)]" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/35 to-black/10" />

          {matchPercentValue != null ? (
            <span
              className={cn(
                "absolute right-3 top-3 z-10 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold shadow-sm",
                "bg-[var(--primary)] text-[var(--primary-foreground)]"
              )}
            >
              <Sparkles className="h-3 w-3" />
              {matchPercentValue}% Match
            </span>
          ) : null}

          <div className="relative flex h-full min-h-[200px] flex-col justify-end p-5 text-white">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/70">
              {country.iso_code}
            </p>
            <h3 className="mt-1 font-[family-name:var(--font-display)] text-2xl tracking-tight md:text-3xl">
              {country.name}
            </h3>
            <div className="mt-3 flex flex-wrap gap-3 text-sm text-white/90">
              <span className="inline-flex items-center gap-1.5">
                <Wallet className="h-3.5 w-3.5" />
                ${country.avg_daily_cost_usd.toFixed(0)}/day
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5" />
                {country.safety_index}/5
              </span>
              {season ? (
                <span className="inline-flex items-center gap-1.5">
                  <Calendar className="h-3.5 w-3.5" />
                  {season}
                </span>
              ) : null}
            </div>
            {!expanded && collapsedTags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {collapsedTags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-white/25 bg-white/10 px-2.5 py-0.5 text-xs backdrop-blur-sm"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-300 ease-out",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        )}
      >
        <div className="overflow-hidden">
          <div className="space-y-5 border-t border-[var(--border)] bg-[var(--card)] px-5 py-5">
            <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
              {country.description}
            </p>

            {tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-[var(--border)] px-2.5 py-0.5 text-xs text-[var(--muted-foreground)]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
                Recommended cities in {country.name}
              </p>
              {topCities.length === 0 ? (
                <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                  No city recommendations yet.
                </p>
              ) : (
                <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {topCities.map((city) => {
                    const cityId =
                      resolveCityId(country.id, city.slug) ?? city.slug;
                    const href = `/planner?city=${encodeURIComponent(cityId)}&country=${encodeURIComponent(country.id)}`;
                    const cityTags = city.tags ?? [];
                    return (
                      <li
                        key={city.slug}
                        className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--background)]/80"
                      >
                        <div className="relative h-28 w-full bg-[var(--muted)]">
                          {city.photo_url ? (
                            <img
                              src={city.photo_url}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                          ) : null}
                        </div>
                        <div className="flex flex-col gap-3 p-4">
                          <div className="flex items-start gap-2">
                            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary)]" />
                            <div className="min-w-0">
                              <p className="font-medium text-[var(--foreground)]">
                                {city.name}
                              </p>
                              {city.description ? (
                                <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-[var(--muted-foreground)]">
                                  {city.description}
                                </p>
                              ) : null}
                            </div>
                          </div>
                          {cityTags.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                              {cityTags.slice(0, 4).map((tag) => (
                                <span
                                  key={tag}
                                  className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          <Button asChild size="sm" className="w-full">
                            <Link href={href} onClick={(e) => e.stopPropagation()}>
                              Plan Trip to {city.name}
                            </Link>
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

/** @deprecated Prefer CountryBrowseCard */
export function DestinationCard({
  index,
  country,
}: {
  index: number;
  country?: Country;
  hit?: SearchHit;
}) {
  if (country) {
    return (
      <CountryBrowseCard
        index={index}
        country={country}
        expanded={false}
        resolveCityId={() => null}
        onToggle={() => undefined}
      />
    );
  }
  return null;
}

export { CountryBrowseCard as CountryCard };
