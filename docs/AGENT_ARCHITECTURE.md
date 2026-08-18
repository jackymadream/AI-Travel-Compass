# Tool-Calling Itinerary Agent Architecture

Phase 3 planner for GenAI Travel Compass. Builds a **day-by-day itinerary** for a single chosen city using a tool-calling agent loop, then emits a **validated structured** `ItineraryResponse`.

Aligns with [`CONTEXT.md`](../CONTEXT.md) §7 (agentic layer) and Phase 2 hybrid search: the city is already inside the frozen candidate set; the agent **must not invent destinations** or relax hard budget/safety rules.

**Contracts:** [`src/schemas/itinerary.py`](../src/schemas/itinerary.py) · **Entry:** [`src/services/agent_service.py`](../src/services/agent_service.py)

---

## 1. End-to-end workflow

```
User Input (ItineraryRequest)
        │
        ▼
┌───────────────────────────────┐
│  Itinerary Agent              │
│  (tool-calling loop)          │
└───────────────┬───────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
 POI Retrieval      Schedule Evaluator
 Tool               Tool
 (grounded POIs)    (pace · budget · slots)
        │                │
        └────────┬───────┘
                 ▼
     Validated Structured Output
     (ItineraryResponse)
```

| Stage | Input | Output | Authority |
|-------|--------|--------|-----------|
| **1. User Input** | `city_id`, `days`, `pace`, `daily_budget_usd`, `preferences`, `locale` | `ItineraryRequest` | Client / API |
| **2. Agent orchestration** | Request + city metadata | Tool calls + draft plan | LLM (propose only) |
| **3a. POI Retrieval Tool** | City + preferences / tags | Grounded POI list (name, category, cost, duration) | DB / RAG **scoped to city** |
| **3b. Schedule Evaluator Tool** | Draft day plans + pace + budget | Pass/fail + fix hints | Deterministic rules |
| **4. Validated Structured Output** | Passing plan + reasoning | `ItineraryResponse` | Schema + evaluator |

The agent may call tools **multiple times** (retrieve → draft → evaluate → revise) until the Schedule Evaluator accepts the plan or a max-iteration limit is hit.

---

## 2. User Input (`ItineraryRequest`)

| Field | Role | Notes |
|-------|------|--------|
| `city_id` | Target destination | Must exist in Postgres; typically from Phase 2 search hit |
| `days` | Trip length | Hard range **1–7** |
| `pace` | Density of day | `relaxed` / `moderate` / `packed` → activity count & rest gaps |
| `daily_budget_usd` | Soft/hard spend ceiling per day | Evaluator rejects days over budget |
| `preferences` | Soft interests | e.g. `food`, `museum`, `nature` → POI retrieval bias |
| `locale` | Narrative language | `en` / `zh-HK` / `ja` (Traditional for zh-HK) |

**Boundary (CONTEXT.md):** Trip duration and itinerary shape are **agentic**. Budget enforcement on *activities* is re-checked by the Schedule Evaluator (defense in depth). The agent must not switch to another city or invent POIs outside retrieval results.

---

## 3. POI Retrieval Tool

**Purpose:** Ground the plan in real places for the requested city.

**Typical inputs:** `city_id`, `preferences[]`, `locale`, optional `category` filter (`attraction` / `food` / `rest`).

**Typical outputs (per POI):**

- `poi_name`, `category`, `cost_usd`, `duration_minutes`, short `description`
- Optional `lat` / `lon` / `address` / `poi_id` / `tags` / `photo_url`

**Rules:**

1. Retrieval is **scoped to `city_id`** (SQL and/or RAG over city-local corpus only). Limit is ~24 per category so multi-day plans can skip already-used stops.
2. Names and cost/duration claims come from tool results — the LLM must not fabricate attraction/rest POIs.
3. Prefer notable POIs (wikipedia/wikidata, museum/castle/attraction tags) over bare `place_of_worship` neighborhood churches.
4. **Hard-skip** `poi_name` / `poi_id` already used on earlier days until that category’s unused pool is empty.
5. Meal slots are **food types** (ramen, monjayaki, …), not restaurant brands. They are injected after retrieval, not taken from the food POI pool.

### 3.1 Itinerary photos

[`src/services/poi_photos.py`](../src/services/poi_photos.py) resolves `photo_url`:

1. Wikidata **P18** (Commons file) when the POI has a `wikidata` id or `wikidata:Q…` tag.
2. Wikipedia REST summary thumbnail only if the page **title tokens overlap** the POI name and, when both have coordinates, they are within ~25 km.
3. Otherwise category-shaped Unsplash stock from [`data/poi_category_photos.json`](../data/poi_category_photos.json) (shrine vs park vs sports — not one Japan postcard list).

Only `upload.wikimedia.org` / Commons FilePath URLs and **allowlisted** Unsplash photo IDs are emitted. The planner UI swaps a 404 image to a category placeholder (`onError`).

Meals use cuisine-keyword Unsplash URLs from the same allowlist (`monjayaki` before generic `sushi`; yakiniku is grilled meat, not Korean BBQ stock).

---

## 4. Schedule Evaluator Tool

**Purpose:** Deterministic validation of draft `DailyItinerary` lists before they leave the agent.

| Check | Rule |
|-------|------|
| Day count | Exactly `request.days` daily plans, `day_number` 1..N contiguous |
| Pace | Count **and** duration must fit `PACE_LIMITS` (includes lunch + dinner). Evaluator adds **30 min travel between consecutive stops**. Moderate: ≤7 activities, ≤600 min; relaxed: ≤5 / 420; packed: ≤10 / 780 |
| Time slots | Non-overlapping `time_slot`s. Lunch is pinned at 12:00 + duration; later stops start after lunch + 30 min; dinner follows the last afternoon stop |
| Meals | Each day has Lunch and Dinner `is_food_slot` activities (`meal_role` lunch / dinner) |
| Cuisine family | Lunch and dinner (and earlier days) do not reuse the same family (sushi, ramen, yakiniku, …) |
| Daily cost | Sum of activity `cost_usd` ≤ `daily_budget_usd` |
| Grounding | Attraction/rest `poi_name`s came from POI Retrieval for this run |
| Uniqueness | Non-meal `poi_name`s are unique across days while unused pool remains |

The Gemini draft prompt repeats those pace caps (count, minutes, travel hops). The evaluator is still the source of truth.

**On failure:** Return structured strings (`Over budget by $N`, `MISSING_MEALS`, `OVERLAPPING_SLOTS`, `Schedule too packed for {pace}…`). The agent revises: drop expensive stops, drop attractions until both pace caps pass, then rebuild slots.

**After `max_turns` (3):**

- **Hard fail** (raises `AgentPlanningError`): over budget, missing lunch/dinner, leftover overlaps.
- **Best effort:** leftover issues are **pace-only** (too many activities or too many minutes). Emit the day with `DailyItinerary.warnings` so the UI can show a schedule note instead of failing the whole trip.

**On success:** Mark the day valid for schema emit.

---

## 5. Validated Structured Output (`ItineraryResponse`)

| Field | Meaning |
|-------|---------|
| `city_name` | Localized city display name |
| `total_cost_usd` | Sum of daily estimated costs |
| `daily_plans` | `list[DailyItinerary]` — theme, cost, optional `warnings[]`, ordered `Activity` rows |
| `agent_reasoning` | Short explanation of pacing / preference trade-offs |

### Nested shapes

- **`Activity`:** `time_slot`, `poi_name`, `category` (`attraction` \| `food` \| `rest`), `cost_usd`, `duration_minutes`, `description`, optional `photo_url` / `lat` / `lon` / `poi_id` / `address`, plus meal flags `is_food_slot` and `meal_role` (`lunch` \| `dinner`)
- **`DailyItinerary`:** `day_number`, `theme`, `estimated_daily_cost`, `warnings` (pace notes after retries), `activities`

Emit after Schedule Evaluator **pass**, or after max turns when only pace caps remain (warnings attached). Parse/validate with Pydantic (`extra` policy + field bounds) at the API boundary.

---

## 6. Agent service entry point

`AgentService.plan_itinerary(request: ItineraryRequest) -> ItineraryResponse` is the application entry ([`src/services/agent_service.py`](../src/services/agent_service.py)).

Live path:

1. Load city metadata (locale-aware name).
2. Retrieve city-scoped POIs (Qdrant `travel_pois` + Supabase `pois`; mock pool when `USE_MOCK_POIS=true`).
3. Draft each day (Gemini Pro when Vertex is configured, else heuristic) with rotated meals and unique photos.
4. Run the Schedule Evaluator; refine until valid or `max_turns`. Pace-only leftovers become day `warnings`; budget / meals / overlaps still fail the request.
5. Emit `ItineraryResponse`. HTTP: `POST /api/v1/itineraries/generate`. Persist via `user_itineraries` when the user is signed in.

Gemini drafts use Vertex (`GEMINI_LOCATION`, usually `us-central1`) even when embeddings stay on `GCP_LOCATION` (`asia-southeast1`). Quality eval (running API): `python scripts/eval_itinerary_flow.py`. The eval checks meals, uniqueness, overlaps, and that a day over the pace cap either fits or carries warnings.

Re-seed Overpass POIs (filters obscure worship; replaces prior overpass rows for that city):

```bash
python scripts/seed_city_pois.py --city tokyo --skip-places --limit 60
```

---

## 7. Relation to Phase 2 / LangGraph

| Layer | Role |
|-------|------|
| Phase 2 `POST /api/v1/search` | Choose **which city** (SQL + Qdrant) |
| Phase 3 itinerary agent | Plan **how to spend days** inside that city |
| CONTEXT.md LangGraph nodes | Broader recommendation graph; this doc specializes **GenerateItinerary** + validation as **tool-calling** |

POI retrieval may reuse Vertex/Qdrant patterns from Phase 2, but collections and filters are **city-scoped**, not destination-discovery.

---

## 8. Non-goals

- Multi-city routes
- Google Places **Photo** API (out of scope; Wikidata/Wikipedia + allowlisted Unsplash only)
