"use client";

import { Star } from "lucide-react";

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
import type { Locale } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";

const LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "zh-HK", label: "繁" },
  { value: "ja", label: "日本語" },
];

type ExploreFiltersProps = {
  maxBudget: number;
  minSafety: number;
  locale: Locale;
  onMaxBudgetChange: (value: number) => void;
  onMinSafetyChange: (value: number) => void;
  onLocaleChange: (value: Locale) => void;
};

export function ExploreFilters({
  maxBudget,
  minSafety,
  locale,
  onMaxBudgetChange,
  onMinSafetyChange,
  onLocaleChange,
}: ExploreFiltersProps) {
  const t = useTranslations("explore");
  return (
    <aside className="flex h-fit flex-col gap-8 rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 p-6 shadow-sm backdrop-blur-sm lg:sticky lg:top-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          {t("filters")}
        </p>
        <h2 className="mt-2 font-[family-name:var(--font-display)] text-2xl text-[var(--foreground)]">
          {t("refine")}
        </h2>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          {t("hardConstraints")}
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <Label htmlFor="max-budget">{t("maxBudget")}</Label>
          <span className="font-[family-name:var(--font-display)] text-lg text-[var(--primary)]">
            ${maxBudget}
            <span className="text-sm text-[var(--muted-foreground)]">/day</span>
          </span>
        </div>
        <Slider
          id="max-budget"
          min={50}
          max={500}
          step={10}
          value={[maxBudget]}
          onValueChange={(value) => onMaxBudgetChange(value[0] ?? 50)}
          aria-label="Maximum daily budget in USD"
        />
        <div className="flex justify-between text-xs text-[var(--muted-foreground)]">
          <span>$50</span>
          <span>$500</span>
        </div>
      </div>

      <div className="space-y-3">
        <Label htmlFor="min-safety">{t("minSafety")}</Label>
        <Select
          value={String(minSafety)}
          onValueChange={(value) => onMinSafetyChange(Number(value))}
        >
          <SelectTrigger id="min-safety" aria-label="Minimum safety rating">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[1, 2, 3, 4, 5].map((rating) => (
              <SelectItem key={rating} value={String(rating)}>
                <span className="inline-flex items-center gap-2">
                  <span className="inline-flex">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star
                        key={i}
                        className={cn(
                          "h-3.5 w-3.5",
                          i < rating
                            ? "fill-[var(--accent)] text-[var(--accent)]"
                            : "text-[var(--border)]"
                        )}
                      />
                    ))}
                  </span>
                  {rating}+
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3">
        <Label>{t("locale")}</Label>
        <div className="grid grid-cols-3 gap-2">
          {LOCALES.map((item) => (
            <Button
              key={item.value}
              type="button"
              size="sm"
              variant={locale === item.value ? "default" : "outline"}
              onClick={() => onLocaleChange(item.value)}
              aria-pressed={locale === item.value}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </div>
    </aside>
  );
}
