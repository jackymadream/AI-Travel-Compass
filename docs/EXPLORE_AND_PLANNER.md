# Explore and Planner — Data Flow

How destination search and itinerary planning work, why each step exists, and which tools sit behind it.

Live: [travel.jackymadream.com](https://travel.jackymadream.com) · Local: [localhost:3000/explore](http://localhost:3000/explore) · [localhost:3000/planner](http://localhost:3000/planner)

---

## 1. Explore

**Job:** turn a natural-language query plus filters into a **shortlist of real cities**. The LLM must not invent destinations.

### Data flow

```
User (Next.js Explore)
        │  query, budget, safety, tags, locale
        ▼
FastAPI  POST /api/v1/search
        │
        ▼
Intent split
  • Hard: budget, safety, tags
  • Soft: vibe / interests (semantic query)
        │
        ├──────────────────┐
        ▼                  ▼
PostgreSQL (Supabase)   Vertex embeddings
SQL candidate set       text-embedding-004
(frozen city IDs)              │
        │                      ▼
        │               Qdrant vector search
        │               (scoped to those IDs only)
        └──────────┬───────────┘
                   ▼
            Score blend
            (similarity + tag overlap)
                   ▼
            SearchResponse → country / city cards
```

1. The UI sends text and optional sliders (`max_budget`, `min_safety`, `tags`, `locale`).
2. **Intent extraction** (rule-based) splits hard constraints from the semantic remainder.
3. **SQL** applies budget, safety, and tags. Cities that fail are dropped. This set is frozen.
4. The remaining query is **embedded** and searched in **Qdrant**, filtered to those city IDs.
5. Scores are blended and returned. Empty SQL → empty results with a reason, not a hallucinated city.

### Why it matters

Hard rules (budget, safety) are **non-negotiable**. If they lived only in a prompt, the model could still recommend a destination the user cannot afford or should not visit. SQL first, vectors second is **hybrid RAG**: retrieval is grounded in a database, then ranked by meaning.

### Tools

| Step | Tool |
|------|------|
| UI | Next.js 15, TypeScript |
| API | FastAPI, Pydantic |
| Hard filters | PostgreSQL (Supabase) |
| Intent split | `src/services/intent_extraction.py` (rules, not an LLM) |
| Embeddings | Google Vertex AI `text-embedding-004` |
| Vector search | Qdrant (`travel_destinations`, 768-d cosine) |
| Optional cache | Redis |

---

## 2. Planner

**Job:** for **one chosen city**, build a day-by-day itinerary that only uses **retrieved POIs** and that **passes schedule and budget checks**.

### Data flow

```
User (Next.js Planner)
        │  city, days, pace, daily budget, preferences, locale
        ▼
FastAPI  POST /api/v1/itineraries/generate
        │
        ▼
Itinerary agent (tool-calling loop, up to ~3 turns per day)
        │
        ├─ Tool: search_pois
        │     PostgreSQL POI metadata + Qdrant POI vectors
        │     scoped to city_id — no invented places
        │
        ├─ Draft day
        │     LLM (Gemini) or heuristic proposer
        │     structured JSON (Pydantic)
        │
        └─ Tool: evaluate_schedule_and_budget
              deterministic Python
              meals, overlaps, budget (hard)
              pace count + minutes including 30 min travel hops
              pass → emit day
              fail → retry; pace-only after 3 turns → emit with warnings
        ▼
ItineraryResponse (timeline + map)
        │
        └─ User can edit / reorder / add custom spots (human-in-the-loop)
```

1. User picks a city (often from Explore) and constraints.
2. **POI retrieval tool** loads grounded places for that city (name, category, cost, duration, coords).
3. A **draft** is proposed. The model may only use retrieved POIs.
4. The **evaluator tool** checks packing, overlaps, and budget. Failures come back as structured violations, not a chat apology.
5. Loop until pass or max turns. **Budget, missing meals, and leftover overlaps** fail the request. **Pace-only** leftovers (too many stops or minutes) still return the day with `warnings` for the timeline.
6. UI shows the plan; the user can still change it.

### Why it matters

A single unconstrained completion will invent restaurants, ignore budget, and double-book the afternoon. **Tools own the facts and the rules; the model only proposes.** That is the agentic pattern: retrieve → draft → validate → retry. The same idea as enterprise RAG + agents: grounded retrieval, tool integration, failure handling, then a human edit if needed.

### Tools

| Step | Tool |
|------|------|
| UI | Next.js, timeline, Leaflet map |
| API | FastAPI `ItineraryAgent` |
| POI retrieval | `search_pois` — PostgreSQL + Qdrant (`travel_pois`) |
| Generation | Vertex AI Gemini (`GEMINI_LOCATION`, typically `us-central1`; embeddings can stay on `GCP_LOCATION`) |
| Contracts | Pydantic `ItineraryRequest` / `ItineraryResponse` |
| Checks | `evaluate_schedule_and_budget` (deterministic, not an LLM) |
| Tests | Pytest on agent and evaluator behaviour |
| Photos / geocode | Wikipedia OpenSearch, Nominatim (custom spots) |
| Deploy | Docker, GCP Cloud Run |

---

## How the two pages connect

Explore answers **where**. Planner answers **what to do there**. Explore’s candidate set is cities; Planner’s candidate set is POIs in one city. Both freeze the candidate set in SQL/vectors **before** generation, so the model cannot expand the world.

**One sentence for interviews:** Explore is hybrid RAG over destinations; Planner is a tool-calling agent over POIs, with a deterministic evaluator so the plan can fail instead of hallucinating.
