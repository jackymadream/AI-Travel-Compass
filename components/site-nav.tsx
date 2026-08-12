"use client";

import Link from "next/link";

import { AuthStatus } from "@/components/auth-status";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/explore", label: "Explore", active: "explore" },
  { href: "/planner", label: "Planner", active: "planner" },
  { href: "/itineraries", label: "My itineraries", active: "itineraries" },
] as const;

type SiteNavProps = {
  active: "explore" | "planner" | "itineraries";
  className?: string;
};

export function SiteNav({ active, className }: SiteNavProps) {
  return (
    <nav
      className={cn(
        "flex flex-wrap items-center justify-between gap-3",
        className
      )}
      aria-label="Primary"
    >
      <div className="flex flex-wrap items-center gap-2">
        {LINKS.map((link) => {
          const isActive = link.active === active;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition-colors",
                isActive
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "border border-[var(--border)] bg-[var(--card)]/80 text-[var(--muted-foreground)] hover:border-[var(--primary)] hover:text-[var(--primary)]"
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
      <AuthStatus />
    </nav>
  );
}
