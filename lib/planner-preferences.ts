/** Curated planner preference chips + searchable taxonomy (mirrors data/interest_taxonomy.json). */

/** Visible primary chips — rare tags live in Search interests. */
export const PRIMARY_PREFERENCE_CHIPS = [
  "food",
  "culture",
  "nightlife",
  "nature",
  "wellness",
  "adventure",
] as const;

/** Mutually exclusive discovery mode. `popular` is on by default. */
export const DISCOVERY_MODES = ["popular", "unconventional"] as const;
export type DiscoveryMode = (typeof DISCOVERY_MODES)[number];

export const DEFAULT_PLANNER_PREFERENCES = [
  "food",
  "culture",
  "popular",
] as const;

export function withDiscoveryMode(
  preferences: string[],
  mode: DiscoveryMode
): string[] {
  const next = preferences.filter(
    (p) => p !== "popular" && p !== "unconventional"
  );
  next.push(mode);
  return next;
}

export function discoveryModeOf(preferences: string[]): DiscoveryMode {
  return preferences.includes("unconventional") ? "unconventional" : "popular";
}

export const ALL_TAXONOMY_TAGS = [
  "culture",
  "food",
  "nature",
  "urban",
  "beach",
  "romance",
  "history",
  "adventure",
  "scenic",
  "wellness",
  "design",
  "outdoors",
  "mountains",
  "nightlife",
  "anime",
  "manga",
  "pop-culture",
  "k-pop",
  "onsen",
  "temples",
  "wine",
  "skiing",
  "hiking",
  "northern-lights",
  "street-food",
  "architecture",
  "festivals",
  "diving",
  "desert",
  "islands",
  "markets",
  "museums",
] as const;

/** Synonym → canonical tag (subset used for free-text mapping). */
export const PREFERENCE_SYNONYMS: Record<string, string> = {
  museum: "museums",
  museums: "museums",
  gallery: "museums",
  anime: "anime",
  manga: "anime",
  otaku: "anime",
  ghibli: "anime",
  onsen: "onsen",
  "hot spring": "onsen",
  "hot springs": "onsen",
  aurora: "northern-lights",
  "northern lights": "northern-lights",
  "street food": "street-food",
  hawker: "street-food",
  temple: "temples",
  temples: "temples",
  shrine: "temples",
  wine: "wine",
  hiking: "hiking",
  trek: "hiking",
  ski: "skiing",
  skiing: "skiing",
  diving: "diving",
  scuba: "diving",
  desert: "desert",
  islands: "islands",
  island: "islands",
  markets: "markets",
  market: "markets",
  nightlife: "nightlife",
  beach: "beach",
  nature: "nature",
  culture: "culture",
  food: "food",
  architecture: "architecture",
  adventure: "adventure",
  history: "history",
  wellness: "wellness",
  urban: "urban",
  "k-pop": "k-pop",
  kpop: "k-pop",
};

export function filterTaxonomyTags(query: string): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return ALL_TAXONOMY_TAGS.filter(
    (tag) =>
      tag.includes(q) ||
      tag.replace(/-/g, " ").includes(q) ||
      Object.entries(PREFERENCE_SYNONYMS).some(
        ([syn, canon]) => canon === tag && syn.includes(q)
      )
  ).slice(0, 8);
}

/** Map free-text into canonical tags + residual soft tokens. */
export function parseFreeTextPreferences(text: string): string[] {
  const raw = text.trim().toLowerCase();
  if (!raw) return [];
  const out: string[] = [];
  let remainder = raw;

  // Longest synonym first
  const synonyms = Object.keys(PREFERENCE_SYNONYMS).sort(
    (a, b) => b.length - a.length
  );
  for (const syn of synonyms) {
    if (remainder.includes(syn)) {
      const canon = PREFERENCE_SYNONYMS[syn];
      if (!out.includes(canon)) out.push(canon);
      remainder = remainder.replaceAll(syn, " ");
    }
  }

  const residual = remainder
    .split(/[,;/|]+|\s{2,}/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 3 && !out.includes(t));
  for (const token of residual) {
    if (!out.includes(token)) out.push(token);
  }
  return out;
}
