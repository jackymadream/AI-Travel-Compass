# Deployment Guide — GenAI Travel Compass

How to run locally with Docker and deploy the FastAPI backend + Next.js frontend.

**Related:** [README](../README.md) · [`.env.example`](../.env.example) · [`scripts/smoke_test.py`](../scripts/smoke_test.py)

**Production hosts:**

| Role | URL |
|------|-----|
| Frontend (Next.js) | https://travel.jackymadream.com |
| API (FastAPI / Cloud Run) | https://api.jackymadream.com |

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

Deploy **backend** and **frontend** as separate services.

- Frontend `NEXT_PUBLIC_API_URL` → `https://api.jackymadream.com`
- Backend `CORS_ORIGINS` → `https://travel.jackymadream.com` (+ localhost for local UI)

### 2.1 FastAPI backend

#### Google Cloud Run (reference deployment)

```bash
gcloud builds submit --config cloudbuild.yaml --project travel-compass-ai
gcloud run deploy ai-travel-backend \
  --image asia-east1-docker.pkg.dev/travel-compass-ai/ai-travel/ai-travel-backend:latest \
  --region asia-east1 \
  --allow-unauthenticated \
  --port 8080 \
  --env-vars-file run-env.yaml
```

Default Cloud Run URL (also works without custom domain):  
`https://ai-travel-backend-209308720273.asia-east1.run.app`

Custom domain: map `api.jackymadream.com` to the Cloud Run service, then in DNS add the CNAME Google shows (typically `api` → `ghs.googlehosted.com`). Use TLS **Full** / **Full (strict)** at your DNS/CDN provider.

Health checks:

- `https://api.jackymadream.com/health/liveness` → `{"status":"alive"}`
- `https://api.jackymadream.com/health` → Redis / Qdrant / Supabase readiness

Update CORS (Cloud Shell / bash — commas need `^;^` delimiter):

```bash
gcloud run services update ai-travel-backend \
  --region asia-east1 \
  --project travel-compass-ai \
  --update-env-vars='^;^CORS_ORIGINS=https://travel.jackymadream.com,http://localhost:3000,http://127.0.0.1:3000'
```

#### Render / Fly.io (alternatives)

Same Docker image (`Dockerfile.backend`), set env vars from the [checklist](#3-environment-variables-checklist), health path `/health/liveness`.

### 2.2 Next.js frontend → Vercel

1. Import this GitHub repo into [Vercel](https://vercel.com).
2. Framework: **Next.js** (repo root).
3. Domain: `travel.jackymadream.com` (CNAME in DNS → value shown in Vercel Domains UI).
4. Production env: `NEXT_PUBLIC_API_URL=https://api.jackymadream.com` (no trailing slash).
5. Deploy. Routes: `/explore`, `/planner`.

Optional local production image:

```bash
docker build -f Dockerfile.frontend \
  --build-arg NEXT_PUBLIC_API_URL=https://api.jackymadream.com \
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
| `GCP_LOCATION` | Backend | e.g. `us-central1` or `asia-southeast1` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Backend | Path to service-account JSON (or cloud IAM) |
| `CORS_ORIGINS` | Backend | `https://travel.jackymadream.com` + localhost |
| `NEXT_PUBLIC_API_URL` | Frontend | Prod: `https://api.jackymadream.com` |

### Recommended / optional

| Variable | Used by | Notes |
|----------|---------|--------|
| `REDIS_URL` | Backend | e.g. `redis://host:6379/0`; falls back to in-memory TTL |
| `VERTEX_EMBEDDING_TIMEOUT_SEC` | Backend | Default `30` |
| `EMBEDDING_DIMENSIONS` | Backend | `256` / `512` / `768` (default 768) |
| `LOG_LEVEL` | Backend | `INFO` / `DEBUG` |
| `GEMINI_API_KEY` | Backend (future LLM) | Optional; heuristic planner works without it |
| `SMOKE_BASE_URL` | Smoke script | Override API URL for `scripts/smoke_test.py` |
| `SMOKE_ALLOW_DEGRADED` | Smoke script | `true` to accept `/health` degraded |

### Vertex / Gemini naming

- Embeddings use **Vertex AI** (`text-embedding-004`) via `GCP_*` + credentials/IAM.
- `GEMINI_API_KEY` is reserved for an optional generative itinerary LLM seam.

---

## 4. Post-deploy verification

1. `GET https://api.jackymadream.com/health/liveness` → `{"status":"alive"}`
2. `GET https://api.jackymadream.com/health` → prefer `status: ok` (degraded OK if Redis optional)
3. `python scripts/smoke_test.py --base-url https://api.jackymadream.com --allow-degraded`
4. Open `https://travel.jackymadream.com/explore` and `/planner`

---

## 5. Security notes

- Never commit `.env`, `credentials/*.json`, or service-role keys.
- Use the **service role** key only on the backend.
- Restrict `CORS_ORIGINS` to known frontend hosts in production.
- Prefer cloud secret managers over baking secrets into images.
