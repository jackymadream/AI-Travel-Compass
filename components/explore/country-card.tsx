import { Shield, Wallet } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Country } from "@/lib/api";

type CountryCardProps = {
  country: Country;
  index: number;
};

export function CountryCard({ country, index }: CountryCardProps) {
  return (
    <Card
      className="animate-fade-up transition-transform duration-300 hover:-translate-y-1"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
              {country.iso_code}
            </p>
            <CardTitle className="mt-1">{country.name}</CardTitle>
          </div>
          <span className="rounded-md bg-[var(--secondary)] px-2 py-1 text-xs font-medium text-[var(--secondary-foreground)]">
            {country.best_travel_season.label}
          </span>
        </div>
        <CardDescription className="line-clamp-2">
          {country.description}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2 rounded-lg bg-[var(--muted)]/70 px-3 py-2">
            <Wallet className="h-4 w-4 text-[var(--primary)]" />
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">Daily budget</p>
              <p className="font-semibold">${country.avg_daily_cost_usd.toFixed(0)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-[var(--muted)]/70 px-3 py-2">
            <Shield className="h-4 w-4 text-[var(--primary)]" />
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">Safety</p>
              <p className="font-semibold">
                {country.safety_index}
                <span className="text-[var(--muted-foreground)]">/5</span>
              </p>
            </div>
          </div>
        </div>

        {country.region_tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {country.region_tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[var(--border)] px-2.5 py-0.5 text-xs text-[var(--muted-foreground)]"
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
