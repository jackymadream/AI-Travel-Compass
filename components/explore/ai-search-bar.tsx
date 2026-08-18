"use client";

import { FormEvent, useState } from "react";
import { Search, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const SEARCH_SUGGESTIONS = [
  "Cozy food city by the sea",
  "Historic autumn vibes",
  "Budget-friendly adventure with nature",
  "Safe luxury city break",
] as const;

type AiSearchBarProps = {
  initialQuery?: string;
  loading?: boolean;
  placeholder?: string;
  onSearch: (query: string) => void;
  onClear: () => void;
};

export function AiSearchBar({
  initialQuery = "",
  loading = false,
  placeholder = "Describe the trip you want…",
  onSearch,
  onClear,
}: AiSearchBarProps) {
  const [query, setQuery] = useState(initialQuery);

  function submit(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    onSearch(trimmed);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit(query);
  }

  return (
    <div className="animate-fade-up rounded-2xl border border-[var(--border)] bg-[var(--card)]/95 p-5 shadow-sm backdrop-blur-sm">
      <div className="mb-3 flex items-center gap-2 text-[var(--primary)]">
        <Sparkles className="h-4 w-4" />
        <p className="text-xs font-semibold uppercase tracking-[0.18em]">
          AI natural language search
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Search destinations</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder}
            className="h-12 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] pl-10 pr-4 text-sm outline-none ring-[var(--ring)] placeholder:text-[var(--muted-foreground)] focus:ring-2"
          />
        </label>
        <div className="flex gap-2">
          <Button type="submit" className="h-12 px-6" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Search"}
          </Button>
          {query.trim() && (
            <Button
              type="button"
              variant="outline"
              className="h-12"
              onClick={() => {
                setQuery("");
                onClear();
              }}
            >
              Clear
            </Button>
          )}
        </div>
      </form>

      <div className="mt-4 flex flex-wrap gap-2">
        {SEARCH_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => submit(suggestion)}
            className={cn(
              "rounded-full border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 text-left text-xs text-[var(--muted-foreground)] transition-colors hover:border-[var(--primary)] hover:text-[var(--primary)]",
              query === suggestion && "border-[var(--primary)] text-[var(--primary)]"
            )}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
