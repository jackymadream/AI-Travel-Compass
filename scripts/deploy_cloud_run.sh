#!/usr/bin/env bash
# Build backend image with Cloud Build and deploy to Cloud Run (asia-east1).
# Usage (Git Bash / WSL):
#   export GCP_PROJECT_ID=travel-compass-ai
#   bash scripts/deploy_cloud_run.sh

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-travel-compass-ai}"
REGION="${GCP_REGION:-asia-east1}"
SERVICE="${CLOUD_RUN_SERVICE:-ai-travel-backend}"
IMAGE="gcr.io/${PROJECT_ID}/ai-travel-backend:latest"

echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Service:  ${SERVICE}"
echo "Image:    ${IMAGE}"

gcloud config set project "${PROJECT_ID}"

# Enable APIs (safe if already enabled)
gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com --project "${PROJECT_ID}"

echo "==> Building & pushing image (Dockerfile.backend)…"
gcloud builds submit --tag "${IMAGE}" -f Dockerfile.backend .

echo "==> Deploying to Cloud Run…"
# Pass secrets via --set-env-vars / Secret Manager in production.
# Minimal deploy matches the requested flags; configure env in Console or extend this script.
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --port 8080 \
  --project "${PROJECT_ID}"

echo "==> Service URL:"
gcloud run services describe "${SERVICE}" \
  --platform managed \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)'
