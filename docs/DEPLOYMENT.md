# Deployment Guide — GenAI Travel Compass

How to run locally with Docker and deploy the FastAPI backend + Next.js frontend to the cloud.

**Related:** [README](../README.md) · [`.env.example`](../.env.example) · [`scripts/smoke_test.py`](../scripts/smoke_test.py)

---

## 1. Local Docker deployment

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- A filled `.env` (copy from `.env.example`)
- GCP service account JSON under `./credentials/` if using Vertex embeddings
- Seeded Supabase schema + Qdrant collection (see README local setup)

### Start the stack

```bash
cp .env.example .env
# edit .env with real secrets

docker compose up --build
```

Services:

| Service | URL |
|---------|-----|
| Backend (FastAPI) | http://localhost:8000 — docs at `/docs` |
| Frontend (Next.js) | http://localhost:3000 — `/explore`, `/planner` |
| Health | http://localhost:8000/health · `/health/liveness` |

Optional Redis:

```bash
docker compose --profile cache up --build
# then set REDIS_URL=redis://redis:6379/0 for the backend service
```

Stop:

```bash
docker compose down
```

### Smoke test (live API)

With the API running:

```bash
pip install -r requirements.txt
python scripts/smoke_test.py --allow-degraded
# or: python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Pipeline: **liveness → readiness → search → itinerary generation**.

---

## 2. Cloud deployment

Deploy **backend** and **frontend** as separate services. Point the frontend’s `NEXT_PUBLIC_API_URL` at the public API URL, and set backend `CORS_ORIGINS` to the frontend origin(s).

### 2.1 FastAPI backend

Pick one host (patterns are equivalent):

#### Render

1. New **Web Service** from this repo.
2. Runtime: Docker → `Dockerfile.backend` (or native: build `pip install -r requirements.txt`, start `uvicorn src.main:app --host 0.0.0.0 --port $PORT`).
3. Set environment variables from the [checklist](#3-environment-variables-checklist).
4. Mount / upload GCP credentials (or use Render secret files) and set `GOOGLE_APPLICATION_CREDENTIALS`.
5. Health check path: `/health/liveness`.

#### Fly.io

```bash
# from repo root (install flyctl first)
fly launch --dockerfile Dockerfile.backend --name travel-compass-api --no-deploy
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... QDRANT_URL=... # etc.
fly deploy --dockerfile Dockerfile.backend
```

Set `[http_service].force_https` and a health check on `/health/liveness` in `fly.toml` if generated.

#### Google Cloud Run

```bash
gcloud builds submit --tag gcr.io/$PROJECT_ID/travel-compass-api -f Dockerfile.backend
gcloud run deploy travel-compass-api \
  --image gcr.io/$PROJECT_ID/travel-compass-api \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "SUPABASE_URL=...,QDRANT_URL=...,CORS_ORIGINS=https://your-app.vercel.app" \
  --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-key:latest,QDRANT_API_KEY=qdrant-key:latest"
```

Mount the Vertex service-account JSON via Secret Manager or Workload Identity. Prefer Workload Identity on GKE/Cloud Run when possible instead of key files.

### 2.2 Next.js frontend → Vercel

1. Import the GitHub repo into [Vercel](https://vercel.com).
2. Framework preset: **Next.js** (root directory = repo root).
3. Environment variable:
   - `NEXT_PUBLIC_API_URL` = `https://<your-api-host>` (no trailing slash)
4. Deploy. Routes: `/explore`, `/planner`.
5. Update backend `CORS_ORIGINS` to include `https://<your-vercel-app>.vercel.app`.

Local production-like frontend image (optional):

```bash
docker build -f Dockerfile.frontend \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  -t travel-compass-web .
```

---

## 3. Environment variables checklist

Copy from [`.env.example`](../.env.example) and fill every required row before production traffic.

### Required (core)

| Variable | Used by | Notes |
|----------|---------|--------|
| `SUPABASE_URL` | Backend | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | Server-only; never expose to the browser |
| `QDRANT_URL` | Backend | Cluster URL |
| `QDRANT_API_KEY` | Backend | Cluster API key |
| `GCP_PROJECT_ID` | Backend | Vertex AI project |
| `GCP_LOCATION` | Backend | Default `us-central1` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Backend | Path to service-account JSON (or use cloud IAM) |
| `CORS_ORIGINS` | Backend | Comma-separated frontend origins |
| `NEXT_PUBLIC_API_URL` | Frontend | Public API base URL |

### Recommended / optional

| Variable | Used by | Notes |
|----------|---------|--------|
| `REDIS_URL` | Backend | e.g. `redis://host:6379/0`; falls back to in-memory TTL |
| `VERTEX_EMBEDDING_TIMEOUT_SEC` | Backend | Default `30` |
| `EMBEDDING_DIMENSIONS` | Backend | `256` / `512` / `768` (default 768) |
| `LOG_LEVEL` | Backend | `INFO` / `DEBUG` |
| `GEMINI_API_KEY` | Backend (future LLM) | Optional live LLM for itinerary agent; heuristic planner works without it |
| `SMOKE_BASE_URL` | Smoke script | Override API URL for `scripts/smoke_test.py` |
| `SMOKE_ALLOW_DEGRADED` | Smoke script | `true` to accept `/health` degraded |

### Vertex / Gemini naming

- Embeddings today use **Vertex AI** (`text-embedding-004`) via `GCP_*` + `GOOGLE_APPLICATION_CREDENTIALS`.
- `GEMINI_API_KEY` is reserved for optional generative itinerary planning (Phase 3 LLM seam); not required for smoke tests that use the heuristic agent.

---

## 4. Post-deploy verification

1. `GET /health/liveness` → `{"status":"alive"}`
2. `GET /health` → prefer `status: ok` (degraded is acceptable if Redis is optional)
3. Run `python scripts/smoke_test.py --base-url https://<api>`
4. Open the Vercel app → Explore search + Planner generate

---

## 5. Security notes

- Never commit `.env`, `credentials/*.json`, or service-role keys.
- Use the **service role** key only on the backend.
- Restrict `CORS_ORIGINS` to known frontend hosts in production.
- Prefer cloud secret managers (Render secrets, Fly secrets, GCP Secret Manager, Vercel env) over baking secrets into images.
