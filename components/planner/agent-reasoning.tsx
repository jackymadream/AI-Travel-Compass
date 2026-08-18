"use client";

import { Clock3, Sparkles, Wallet } from "lucide-react";

import type { ItineraryResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type AgentReasoningPanelProps = {
  response: ItineraryResponse;
  className?: string;
};

export function AgentReasoningPanel({
  response,
  className,
}: AgentReasoningPanelProps) {
  const summary = response.user_summary || response.agent_reasoning;
  const tips = response.prep_tips || [];

  return (
    <aside
      className={cn(
        "animate-fade-up rounded-2xl border border-[var(--border)] bg-[var(--card)]/95 p-5 shadow-sm backdrop-blur-sm",
        className
      )}
    >
      <div className="mb-3 flex items-center gap-2 text-[var(--primary)]">
        <Sparkles className="h-4 w-4" />
        <p className="text-xs font-semibold uppercase tracking-[0.18em]">
          Trip insights
        </p>
      </div>
      <p className="text-sm leading-relaxed text-[var(--foreground)]">{summary}</p>
      {tips.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
            Before you go
          </p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-sm text-[var(--muted-foreground)]">
            {tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3 text-xs text-[var(--muted-foreground)]">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--secondary)] px-3 py-1 text-[var(--secondary-foreground)]">
          <Wallet className="h-3.5 w-3.5" />
          Total ${response.total_cost_usd.toFixed(0)}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--muted)] px-3 py-1">
          <Clock3 className="h-3.5 w-3.5" />
          {response.daily_plans.length} day
          {response.daily_plans.length === 1 ? "" : "s"} · {response.city_name}
        </span>
      </div>
    </aside>
  );
}
