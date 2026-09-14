"use client";

import { useEffect, useState } from "react";

type ItineraryProgressProps = {
  percent: number;
  step: string;
  stepLabel: string;
  dayNumber?: number;
  totalDays?: number;
  detail?: string | null;
};

/** Next backend milestone percent for the current step (matches agent_service). */
function nextSectionPercent(
  step: string,
  dayNumber: number | undefined,
  totalDays: number | undefined,
  serverPercent: number
): number {
  const days = Math.max(1, totalDays ?? 1);
  const day = Math.max(1, dayNumber ?? 1);

  switch (step) {
    case "starting":
      return 15;
    case "poi_retrieval":
      return serverPercent < 25 ? 25 : 25 + Math.floor((1 / days) * 60);
    case "plan_day":
    case "draft_day":
    case "validate_day":
      if (day < days) {
        return 25 + Math.floor((day / days) * 60);
      }
      return 92;
    case "finalize":
      return 100;
    case "complete":
      return 100;
    default:
      return Math.min(100, serverPercent + 8);
  }
}

function stripTrailingEllipsis(label: string): string {
  return label.replace(/[.…]+$/u, "").trimEnd();
}

function LoadingStepLabel({ label }: { label: string }) {
  const base = stripTrailingEllipsis(label);

  return (
    <p className="font-medium text-[var(--primary)]">
      <span className="animate-soft-pulse">{base}</span>
      <span className="loading-dots ml-0.5 inline-flex gap-0.5" aria-hidden>
        <span>.</span>
        <span>.</span>
        <span>.</span>
      </span>
    </p>
  );
}

export function ItineraryProgress({
  percent,
  step,
  stepLabel,
  dayNumber,
  totalDays,
  detail,
}: ItineraryProgressProps) {
  const serverPercent = Math.min(100, Math.max(0, Math.round(percent)));
  const [displayPercent, setDisplayPercent] = useState(serverPercent);

  useEffect(() => {
    setDisplayPercent((prev) => Math.max(prev, serverPercent));
  }, [serverPercent]);

  useEffect(() => {
    if (step === "complete" || serverPercent >= 100) {
      setDisplayPercent(100);
      return;
    }

    const ceiling = Math.max(
      serverPercent,
      nextSectionPercent(step, dayNumber, totalDays, serverPercent) - 1
    );

    const id = window.setInterval(() => {
      setDisplayPercent((prev) => {
        const floored = Math.max(prev, serverPercent);
        if (floored >= ceiling) return floored;
        return floored + 1;
      });
    }, 1000);

    return () => window.clearInterval(id);
  }, [serverPercent, step, dayNumber, totalDays]);

  const clamped = Math.min(
    100,
    Math.max(
      serverPercent,
      step === "complete" ? 100 : displayPercent
    )
  );

  return (
    <div
      className="animate-fade-up rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 px-5 py-6"
      role="status"
      aria-live="polite"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="flex items-baseline justify-between gap-3">
        {step === "complete" ? (
          <p className="font-medium text-[var(--primary)]">{stepLabel}</p>
        ) : (
          <LoadingStepLabel label={stepLabel} />
        )}
        <p className="text-sm tabular-nums text-[var(--muted-foreground)]">
          {clamped}%
        </p>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--border)]"
        aria-hidden
      >
        <div
          className="h-full rounded-full bg-[var(--primary)] transition-[width] duration-500 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
      {detail ? (
        <p className="mt-3 text-sm text-[var(--muted-foreground)]">{detail}</p>
      ) : null}
    </div>
  );
}
