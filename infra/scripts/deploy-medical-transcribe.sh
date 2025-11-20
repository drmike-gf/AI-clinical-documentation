#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-automations-n8n-463018}"
REGION="${REGION:-us-central1}"
IMAGE_REGION="${IMAGE_REGION:-us-central1}"
SERVICE="${SERVICE:-medical-transcribe}"
AR_REPO="${AR_REPO:-${IMAGE_REGION}-docker.pkg.dev/${PROJECT_ID}/audio-pipelines}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
IMAGE="${AR_REPO}/${SERVICE}:${TAG}"

gcloud auth configure-docker "${IMAGE_REGION}-docker.pkg.dev" -q
gcloud builds submit apps/${SERVICE} --tag "$IMAGE"

gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --no-allow-unauthenticated \
  --service-account="audio-prep-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},REGION=global,OUTPUT_BUCKET=phi-output-encounters,OUTPUT_PREFIX=transcripts/,PREPPED_BUCKET=phi-inbound-audio-raw,PREPPED_PREFIX=prepped/,SPEECH_MODEL=medical_conversation"
