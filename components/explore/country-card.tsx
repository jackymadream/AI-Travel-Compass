import { Shield, Sparkles, Wallet } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { matchPercent, type Country, type SearchHit } from "@/lib/api";
import { cn } from "@/lib/utils";

type DestinationCardProps = {
  index: number;
  country?: Country;
  hit?: SearchHit;
};

export function DestinationCard({ index, country, hit }: DestinationCardProps) {
  const isSearch = Boolean(hit);
  const name = hit?.name ?? country?.name ?? "";
  const description = hit?.description ?? country?.description ?? "";
  const iso = hit?.iso_code ?? country?.iso_code ?? "";
  const budget = hit?.avg_daily_cost_usd ?? country?.avg_daily_cost_usd ?? 0;
  const safety = hit?.safety_index ?? country?.safety_index ?? 0;
  const tags = hit?.tags ?? country?.region_tags ?? [];
  const seasonLabel = country?.best_travel_season.label;
  const percent = hit ? matchPercent(hit.score) : null;

  return (
    <Card
      className="animate-fade-up transition-transform duration-300 hover:-translate-y-1"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
              {iso}
            </p>
            <CardTitle className="mt-1">{name}</CardTitle>
          </div>
          {percent != null ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold",
                "bg-[var(--primary)] text-[var(--primary-foreground)]"
              )}
            >
              <Sparkles className="h-3 w-3" />
              {percent}% Match
            </span>
          ) : seasonLabel ? (
            <span className="rounded-md bg-[var(--secondary)] px-2 py-1 text-xs font-medium text-[var(--secondary-foreground)]">
              {seasonLabel}
            </span>
          ) : null}
        </div>
        <CardDescription className="line-clamp-2">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2 rounded-lg bg-[var(--muted)]/70 px-3 py-2">
            <Wallet className="h-4 w-4 text-[var(--primary)]" />
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">Daily budget</p>
              <p className="font-semibold">${budget.toFixed(0)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-[var(--muted)]/70 px-3 py-2">
            <Shield className="h-4 w-4 text-[var(--primary)]" />
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">Safety</p>
              <p className="font-semibold">
                {safety}
                <span className="text-[var(--muted-foreground)]">/5</span>
              </p>
            </div>
          </div>
        </div>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-xs",
                  isSearch
                    ? "border-[var(--primary)]/40 bg-[var(--secondary)] text-[var(--secondary-foreground)]"
                    : "border-[var(--border)] text-[var(--muted-foreground)]"
                )}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** @deprecated Prefer DestinationCard — kept for import compatibility */
export { DestinationCard as CountryCard };
