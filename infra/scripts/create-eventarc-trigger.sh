#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-automations-n8n-463018}"
RUN_REGION="${RUN_REGION:-us-central1}"   # Cloud Run region
EA_LOC="${EA_LOC:-us}"                    # Eventarc location (matches US multi‑region bucket)
SERVICE="${SERVICE:-medical-transcribe}"
TRIGGER_NAME="${TRIGGER_NAME:-med-transcribe-trigger}"
BUCKET="${BUCKET:-phi-inbound-audio-raw}"
TRIGGER_SA="${TRIGGER_SA:-audio-prep-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

# Allow trigger SA to invoke the service (idempotent)
gcloud run services add-iam-policy-binding "$SERVICE" \
  --region="$RUN_REGION" \
  --member="serviceAccount:${TRIGGER_SA}" \
  --role="roles/run.invoker" || true

# Create trigger in 'us' for GCS (US multi‑region)
if gcloud eventarc triggers describe "$TRIGGER_NAME" --location="$EA_LOC" >/dev/null 2>&1; then
  echo "Trigger exists: $TRIGGER_NAME in $EA_LOC"; exit 0
fi

gcloud eventarc triggers create "$TRIGGER_NAME" \
  --location="$EA_LOC" \
  --destination-run-service="$SERVICE" \
  --destination-run-region="$RUN_REGION" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=${BUCKET}" \
  --service-account="${TRIGGER_SA}"
