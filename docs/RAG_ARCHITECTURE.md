# Hybrid RAG Architecture

Phase 2 search engine for GenAI Travel Compass. Aligns with [`CONTEXT.md`](../CONTEXT.md): **hard constraints live in SQL**; **semantic preference lives in vectors + ranking**.

**Related:** Qdrant collection `travel_destinations` (768-d Cosine, `text-embedding-004`); Postgres tables `countries` / `cities`.

---

## 1. End-to-end flow

```
Natural Language Query
        │
        ▼
┌───────────────────────────────┐
│  Intent Extraction /          │
│  Decomposition                │
│  • Hard Filters (budget,      │
│    safety, exclusions, tags)  │
│  • Semantic Query (vibe,      │
│    interests, free-text)      │
└───────────────┬───────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
 Supabase SQL      Qdrant Vector
 Filtering         Search
 (candidate IDs)   (scoped to candidates)
        │               │
        └───────┬───────┘
                ▼
        Score Ranking
        (blend filter fit + similarity)
                ▼
        Search Response
```

### Pipeline stages

| Stage | Input | Output | Authority |
|-------|--------|--------|-----------|
| **1. NL Query** | User text + optional explicit filters | Raw request | Client |
| **2. Intent Extraction / Decomposition** | Query string, locale, session overrides | Hard filter set + semantic query string | App / LLM (extract only) |
| **3a. Supabase SQL Filtering** | Hard filters | Frozen **candidate set** (city/country IDs) | PostgreSQL only |
| **3b. Qdrant Vector Search** | Semantic query embedding + candidate ID filter | Ranked hits with similarity scores | Qdrant, **scoped to candidates** |
| **4. Score Ranking** | SQL rows + vector scores + tag overlap | Ordered shortlist | Deterministic blend (no inventing destinations) |
| **5. Response** | Shortlist + locale | `SearchResponse` | API |

---

## 2. Intent Extraction / Decomposition

Split the user utterance into two disjoint parts.

### 2.1 Hard Filters (deterministic)

Mapped to SQL / payload predicates. Never inferred as “soft” ranking alone.

| Signal | Request / extracted field | Store / predicate |
|--------|---------------------------|-------------------|
| Daily budget ceiling | `max_budget` | `avg_daily_cost_usd <= max_budget` |
| Minimum safety | `min_safety` | `safety_index >= min_safety` |
| Interest / region tags | `tags[]` | Overlap with `cities.tags` / `countries.region_tags` (SQL or post-filter) |
| Locale | `locale` | Response language + embedding locale preference |
| Exclusions (future) | session / profile | `NOT IN` country/city IDs |

Explicit request fields **override** or **merge** with values extracted from NL (session wins over profile; explicit API params win over extracted defaults — see `CONTEXT.md` §8).

### 2.2 Semantic Query (vector)

Residue after hard signals are removed, e.g.:

> “quiet coastal city for food lovers under $100/day, safety 4+”

| Part | Classification |
|------|----------------|
| under $100/day | Hard → `max_budget=100` |
| safety 4+ | Hard → `min_safety=4` |
| quiet coastal / food lovers | Soft → semantic query (+ optional `tags: ["food"]`) |

The semantic string is embedded (same model as indexing: Vertex `text-embedding-004`) and used only for Qdrant similarity.

**Rule:** Decomposition must not invent destinations. It only produces filters + a text query.

---

## 3. Supabase SQL Filtering

Runs **before** (or in parallel with, then intersected with) vector search. Produces the frozen candidate set.

```text
WHERE is_active
  AND avg_daily_cost_usd <= :max_budget     -- if set
  AND safety_index >= :min_safety           -- if set
  AND tags / region_tags overlap :tags      -- if set
```

- Prefer **city-level** rows for destination search; join `countries` for ISO / region context.
- Empty candidate set → return structured empty `SearchResponse` with reason codes; **do not** call LLM to invent places; optional: still skip Qdrant.

---

## 4. Qdrant Vector Search

| Setting | Value |
|---------|--------|
| Collection | `travel_destinations` |
| Metric | Cosine |
| Dims | 768 (`text-embedding-004`) |
| Payload keys | `city_id`, `country_id`, `tags`, `daily_budget`, `locale`, … |

**Mandatory scope:** Qdrant `filter` must restrict to candidate `city_id` / `country_id` from SQL. Never retrieve outside the candidate set (`CONTEXT.md` §7.1).

Prefer matching `locale` payload to request `locale` when multiple points exist per destination.

---

## 5. Score Ranking

Blend (weights TBD in later steps; stub uses placeholders):

```text
final_score = α * vector_similarity
            + β * tag_overlap
            + γ * budget_headroom   # optional soft nudge within hard-pass set
```

- Only destinations in the SQL candidate set may appear.
- Stable tie-break: higher safety, then lower `avg_daily_cost_usd`, then `id`.
- Typical `limit`: 5–10 for API shortlist.

---

## 6. Response

`SearchResponse` returns ordered hits with:

- Localized name / description (`locale`)
- Hard-filter fields used (`max_budget`, `min_safety`, …)
- Similarity / rank metadata for debugging
- Optional extracted intent summary (hard vs semantic) for transparency

---

## 7. Boundary rules (non-negotiable)

1. SQL is sole authority for hard inclusion/exclusion.
2. Vector search cannot expand the candidate set.
3. Soft preferences influence order and rationale only.
4. Ground scores and facts in DB + RAG payloads; no hallucinated destinations.
5. `zh-HK` copy remains Traditional Chinese.

---

## 8. Implementation map (Phase 2)

| Artifact | Role |
|----------|------|
| `src/schemas/search.py` | `SearchRequest` / `SearchResponse` contracts |
| `src/services/search_service.py` | Hybrid orchestration stub |
| Later | Intent LLM node, live Supabase + Qdrant clients, FastAPI `/api/v1/search` |
| `src/services/rag_service.py` | Vertex `get_query_embedding` + Qdrant `search_vector_candidates` (payload-scoped) |

---

## 9. Change log

| Date | Change |
|------|--------|
| 2026-08-10 | Initial hybrid RAG architecture for Phase 2 Step 1. |
| 2026-08-10 | Step 3: `SearchService` wires Supabase SQL candidates → `RagService` → localized `SearchResponse`. |
