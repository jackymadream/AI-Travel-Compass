# GenAI Travel Compass — Domain Model & Glossary

This document is the **single source of truth** for domain terminology, business rules, and recommendation pipeline semantics. Developers and AI agents MUST treat definitions here as authoritative when implementing filters, prompts, or graph nodes.

**Related artifact:** `[schema.sql](./schema.sql)` (PostgreSQL tables: `countries`, `cities`, `user_profiles`).

---

## 1. Core Entities


| Term                       | Definition                                                                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Destination**            | A recommendable place. Implemented as a `city` row; its parent `country` provides national context.                                           |
| **Country**                | Top-level destination with ISO code, multilingual metadata, safety index, average daily cost, best travel season, and optional `region_tags`. |
| **City**                   | City-level destination belonging to one country (`country_id` FK). May override country-level signals (safety, cost, season).                 |
| **User Profile**           | Persisted preferences and constraints for a traveler (`user_profiles`).                                                                       |
| **Recommendation Session** | Ephemeral request context (application layer): session overrides merged onto profile before SQL runs. Not a DB table yet.                     |
| **Candidate Set**          | Destinations that survive deterministic SQL pre-filtering. **Fixed input** to the agentic layer; LLM cannot expand it.                        |
| **I18n Text**              | JSONB object with required keys: `en`, `zh-HK`, `ja`. Validated by `is_valid_i18n_text()`; read via `i18n_text_at(column, locale)`. **`zh-HK` MUST be Traditional Chinese (never Simplified).** |


### 1.1 Canonical Field Names

Domain terms used in product copy map to schema columns as follows. Use **schema names in code and SQL**.


| Domain term                  | Schema column                             | Table(s)                          |
| ---------------------------- | ----------------------------------------- | --------------------------------- |
| Daily budget (ceiling)       | `budget_max_usd`                          | `user_profiles`, session override |
| Daily budget (floor)         | `budget_min_usd`                          | `user_profiles`, session override |
| Destination daily cost       | `avg_daily_cost_usd`                      | `countries`, `cities`             |
| Safety rating (destination)  | `safety_index`                            | `countries`, `cities` (1–5)       |
| Minimum safety rating (user) | `min_safety_index`                        | `user_profiles`, session override |
| Trip duration                | `typical_trip_days` / session `trip_days` | `user_profiles`, session override |


---

## 2. Constraint Taxonomy

Preferences are classified by **enforceability**. Hard rules eliminate candidates in SQL; soft rules influence ranking and LLM prose only.

```
User Input
    │
    ├─ Hard Constraints ──► SQL WHERE (must pass)
    ├─ Hard Exclusions  ──► SQL WHERE (must pass)
    └─ Soft Preferences ──► Agentic scoring + LLM (never in SQL WHERE)
```

---

## 3. Hard Constraints

Hard constraints are **non-negotiable**. A destination that fails any hard constraint MUST NOT appear in the candidate set or final recommendations.

### 3.1 Daily Budget Limit


| Field            | Source                              | Rule                                         |
| ---------------- | ----------------------------------- | -------------------------------------------- |
| `budget_max_usd` | `user_profiles` or session override | `cities.avg_daily_cost_usd` ≤ ceiling.       |
| `budget_min_usd` | `user_profiles` (optional)          | If set, `cities.avg_daily_cost_usd` ≥ floor. |


**Business rules:**

1. Budget comparison uses **city-level** `avg_daily_cost_usd`; country-level cost applies only for country-only recommendations.
2. Session override wins over profile when both set a budget.
3. NULL `budget_max_usd` → no upper budget filter.
4. Budget is **USD** only unless currency support is added later.
5. LLM MUST NOT recommend a destination excluded by budget. `ValidateHardRules` re-checks programmatically (defense in depth).

### 3.2 Minimum Safety Index


| Field              | Source                              | Rule                                   |
| ------------------ | ----------------------------------- | -------------------------------------- |
| `min_safety_index` | `user_profiles` or session override | `cities.safety_index` ≥ minimum (1–5). |


**Business rules:**

1. Use city `safety_index` for city recommendations.
2. Default when unset: **3** (schema default on `user_profiles.min_safety_index`).
3. Safety is a hard SQL gate, not a soft weight.

### 3.3 Trip Duration


| Field               | Source                 | Rule                                       |
| ------------------- | ---------------------- | ------------------------------------------ |
| `typical_trip_days` | `user_profiles`        | Baseline trip length (days).               |
| Session `trip_days` | Recommendation session | Overrides profile for the current request. |


**Business rules:**

1. Trip duration is **agentic-only** by default—it does NOT appear in SQL `WHERE` clauses.
2. LLM uses `trip_days` for itinerary depth and pacing.
3. Minimum valid value: **1 day**.

---

## 4. Hard Exclusions

Hard exclusions remove destinations regardless of other preferences. Applied in SQL only.


| Concept                | Storage                                                       | Rule                                              |
| ---------------------- | ------------------------------------------------------------- | ------------------------------------------------- |
| **Excluded countries** | `user_profiles.excluded_country_ids[]` + session override     | `cities.country_id` NOT IN merged exclusion list. |
| **Excluded cities**    | `user_profiles.excluded_city_ids[]` + session override        | `cities.id` NOT IN merged exclusion list.         |
| **Excluded regions**   | Session `excluded_region_tags[]` vs `countries.region_tags[]` | Country tag overlap → exclude all its cities.     |


**Business rules:**

1. Exclusions are absolute; LLM cannot override.
2. Effective list = `UNION(profile exclusions, session exclusions)`.
3. Excluding a country cascades to all its cities via `country_id`.
4. Natural-language exclusions ("no Japan") MUST be resolved to UUIDs before SQL runs.

---

## 5. Soft Preferences

Soft preferences **MUST NOT** appear in mandatory SQL `WHERE` clauses. They influence agentic scoring and LLM narrative only.


| Field                                             | Examples / role                                                             |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| `travel_styles[]`                                 | `adventure`, `relaxation`, `cultural`, `food`, `family`, `luxury`, `budget` |
| `dietary_preferences[]`                           | `vegetarian`, `vegan`, `halal`, `kosher`, `gluten_free`, `nut_allergy`      |
| `party_size`                                      | Companion type: solo (1), couple (2), family/group (≥3/≥4)                  |
| `preferred_seasons[]`, `preferred_months[]`       | Season alignment scoring (agentic)                                          |
| `preferred_country_ids[]`, `preferred_city_ids[]` | Boost favorites (agentic)                                                   |
| `interests[]`                                     | Soft tag overlap for ranking and RAG (see interest taxonomy)                |
| `cities.tags[]`                                   | Destination soft tags: travel styles + specialty interests                  |
| `accessibility_needs[]`                           | Strong soft signal for itinerary design                                     |
| `personalization_notes`                           | Free-text LLM context; cannot bypass hard rules                             |
| `preferred_locale`                                | Output language: `en`, `zh-HK` (Traditional Chinese), `ja`                  |

### 5.1 Interest taxonomy (canonical tags)

Controlled vocabulary lives in [`data/interest_taxonomy.json`](./data/interest_taxonomy.json):

- **Travel styles:** `culture`, `food`, `nature`, `urban`, `beach`, `romance`, `history`, `adventure`, `scenic`, `wellness`, `design`, `outdoors`, `mountains`, `nightlife`.
- **Specialty interests:** `anime`, `manga`, `pop-culture`, `k-pop`, `onsen`, `temples`, `wine`, `skiing`, `hiking`, `northern-lights`, `street-food`, `architecture`, `festivals`, `diving`, `desert`, `islands`, `markets`, `museums`.

Rule-based NL search extracts specialty/style synonyms into soft `interests` and expands the semantic query. **Interests MUST NOT be applied as hard SQL `tags` gates** (they only affect ranking + embeddings).

---

## 6. Deterministic Filtering (PostgreSQL)

**Scope:** Hard constraints, hard exclusions, and active-destination checks only.

**Out of scope:** Travel style, dietary, interests, season preference scoring, trip duration, companion type, and natural-language reasoning.

All hard rules MUST complete in SQL **before the LangGraph graph is invoked**. If the candidate set is empty, return a structured error—**do not call the LLM**.

### 6.1 Pipeline (runs outside LangGraph)

```
Merge user_profiles + session overrides
        ↓
Execute SQL candidate query (cities JOIN countries)
        ↓
Apply hard predicates only (active, budget, safety, exclusions)
        ↓
Stable ORDER BY + LIMIT (deterministic tie-breakers only, e.g. avg_daily_cost_usd ASC)
        ↓
Emit Candidate Set (frozen) → enter LangGraph
```

### 6.2 Mandatory SQL Predicates

```sql
SELECT c.*, co.*
FROM cities c
JOIN countries co ON co.id = c.country_id
WHERE c.is_active = TRUE
  AND co.is_active = TRUE
  AND c.safety_index >= :min_safety_index
  AND (:budget_max_usd IS NULL OR c.avg_daily_cost_usd <= :budget_max_usd)
  AND (:budget_min_usd IS NULL OR c.avg_daily_cost_usd >= :budget_min_usd)
  AND NOT (c.country_id = ANY(:excluded_country_ids))
  AND NOT (c.id = ANY(:excluded_city_ids))
  AND NOT (co.region_tags && :excluded_region_tags)  -- overlap operator
ORDER BY c.avg_daily_cost_usd ASC, c.id ASC
LIMIT :candidate_limit;
```

`:excluded_country_ids` and `:excluded_city_ids` are merged profile + session arrays. Empty arrays match nothing (no exclusion).

### 6.3 SQL Design Principles

1. **Fail closed:** Invalid constraint values (e.g. `min_safety_index` outside 1–5) → reject request.
2. **No LLM in this path:** SQL is the sole authority for inclusion/exclusion.
3. **Index-aware:** Use `idx_cities_safety_cost`, `idx_cities_safety_index`, `idx_cities_avg_daily_cost_usd`, `idx_cities_country_id`, and GIN indexes on exclusion arrays.
4. **No soft scoring in SQL:** Do not rank by `travel_styles`, `interests`, or season preference in this query.
5. **Empty set:** Return reason codes (`BUDGET_TOO_LOW`, `SAFETY_TOO_STRICT`, `ALL_EXCLUDED`); skip LLM.

### 6.4 I18n in SQL

Multilingual fields are JSONB. Read localized strings in application code or SQL:

```sql
SELECT i18n_text_at(c.name, 'zh-HK'::locale_code) AS name_zh_hk
FROM cities c;
```

Filtering uses numeric/array columns (`safety_index`, `avg_daily_cost_usd`), not localized text.

---

## 7. Agentic Recommendation (RAG + LangGraph)

**Scope:** Soft preference scoring, RAG retrieval, ranking, itinerary generation, localized narrative.

**Input:** Frozen candidate set from §6 (city IDs + joined country metadata).

**Must never:** Query destinations outside the candidate set, relax hard constraints, or invent destinations not in PostgreSQL.

### 7.1 Boundary Contract


| Responsibility                     | Deterministic SQL (§6) | Agentic LLM (§7)                     |
| ---------------------------------- | ---------------------- | ------------------------------------ |
| Budget ceiling/floor               | ✅ Filter               | ❌ Re-check only in ValidateHardRules |
| Minimum safety index               | ✅ Filter               | ❌ Re-check only in ValidateHardRules |
| Country/city/region exclusions     | ✅ Filter               | ❌ Must not suggest excluded places   |
| Active destinations                | ✅ Filter               | ❌                                    |
| Travel style / dietary / interests | ❌                      | ✅ Score + narrative                  |
| Season preference alignment        | ❌                      | ✅ Score + narrative                  |
| Trip duration / itinerary          | ❌                      | ✅ Generate                           |
| Localized descriptions             | ❌ (storage only)       | ✅ Read via RAG / `i18n_text_at`      |
| Candidate set membership           | ✅ Authoritative        | ❌ Cannot expand without new SQL run  |


**Entry rule:** LangGraph starts only when §6 returns ≥1 candidate (or explicitly handles the zero-candidate error path without LLM).

### 7.2 Graph Nodes

1. **ReceiveCandidates** — Accept frozen candidate set + merged profile/session context. No DB scan beyond provided rows.
2. **Retrieve** — RAG over `description` I18n JSONB and external corpus for candidate IDs only.
3. **ScorePreferences** — Weight soft signals (`travel_styles`, `interests`, seasons, companion type).
4. **Rank** — Order shortlist (typically 3–5) using scores + retrieved facts.
5. **GenerateItinerary** — Day-by-day plan using session `trip_days`, dietary, and accessibility notes.
6. **ValidateHardRules** — Programmatic re-check of budget, safety, and exclusions on final picks. On failure → **Rank** or abort; never substitute an out-of-set destination.
7. **FormatResponse** — Output in `preferred_locale`; fall back to `en`.

### 7.3 Agent Rules

1. **Grounding:** Names, costs, and safety claims MUST come from candidate row data or RAG chunks.
2. **Hard rule supremacy:** Narrative cannot praise or recommend excluded or filtered destinations.
3. **No set expansion:** Adding destinations requires a new §6 SQL run (e.g. user confirms **WidenSearch** with relaxed *soft* params only).
4. **Uncertainty:** State gaps explicitly; do not fabricate suitability.

### 7.4 RAG Contract

- **Keys:** `city.id`, `country.iso_code`, `interests` tags.
- **Sources:** `cities.description`, `countries.description` (locale slice from JSONB), optional external guides.
- **Scope:** Candidate IDs only.
- **Locale:** `i18n_text_at(field, preferred_locale)`.

---

## 8. Session Override Precedence

1. Session hard constraints (`budget_max_usd`, `budget_min_usd`, `min_safety_index`, `trip_days`)
2. Session hard exclusions (`excluded_country_ids`, `excluded_city_ids`, `excluded_region_tags`)
3. Profile defaults (`user_profiles` columns)
4. Soft preferences (merge arrays; no session override unless explicitly added)

---

## 9. Schema Reference (keys, FKs, indexes)


| Table           | Primary key                   | Foreign keys                 | Budget / safety indexes                                                                                                |
| --------------- | ----------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `countries`     | `id` (UUID)                   | —                            | `idx_countries_safety_index`, `idx_countries_avg_daily_cost_usd`, `idx_countries_safety_cost`                          |
| `cities`        | `id` (UUID)                   | `country_id → countries(id)` | `idx_cities_safety_index`, `idx_cities_avg_daily_cost_usd`, `idx_cities_safety_cost`, `idx_cities_country_cost_safety`, `idx_cities_tags_gin` |
| `user_profiles` | `id` (UUID); unique `user_id` | — (auth external)            | `idx_user_profiles_min_safety_index`, `idx_user_profiles_budget_range`                                                 |


I18n JSONB indexes: per-locale B-tree on `(name->>'en'|'zh-HK'|'ja')` plus GIN `jsonb_path_ops` on `name` and `description` for `countries` and `cities`.

---

## 10. Glossary (Quick Reference)


| Term                        | Meaning                                                            |
| --------------------------- | ------------------------------------------------------------------ |
| **Hard constraint**         | Eliminated in SQL; mandatory pass.                                 |
| **Hard exclusion**          | User-blocked country/city/region; eliminated in SQL.               |
| **Soft preference**         | Agentic scoring + LLM only; never alone in SQL WHERE.              |
| **Candidate set**           | SQL output; frozen input to LangGraph.                             |
| **Safety index / rating**   | Destination score 1–5 (`safety_index`).                            |
| **Daily budget**            | User ceiling `budget_max_usd` vs destination `avg_daily_cost_usd`. |
| **Deterministic filtering** | §6 PostgreSQL pre-filter; no LLM.                                  |
| **Agentic recommendation**  | §7 LangGraph + RAG over candidate set only.                        |


---

## 11. Change Log


| Date       | Change                                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------------------------ |
| 2026-08-06 | Initial domain model.                                                                                              |
| 2026-08-06 | Aligned terminology with schema; added SQL/agent boundary contract; exclusion columns and `region_tags` in schema. |
| 2026-08-18 | Itinerary meals are **catalog food POIs** (`source=cuisine_catalog`) with seeded photos; lunch/dinner picked from the SQL pool. Attraction/rest photos are resolved at **ingest** (Wikidata/Wikipedia/Places) into `pois.photo_url`; the planner copies stored URLs only. |
| 2026-08-26 | **Approach A** multi-city signatures in `data/city_signature_pois.json` (tokyo + osaka/kyoto/seoul/paris/rome/barcelona/bangkok/london/marrakech/reykjavik). Reseed with `--limit 120`. Planner meals/custom stops use category icons by default; Image URL remains editable. |
| 2026-08-06 | Documented `cities.tags`; `zh-HK` I18n must be Traditional Chinese.                                                |


