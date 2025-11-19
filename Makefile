PROJECT_ID ?= automations-n8n-463018
REGION ?= us-central1
SERVICE ?= audio-prep
IMG ?= us-central1-docker.pkg.dev/$(PROJECT_ID)/audio-pipelines/$(SERVICE):$(shell git rev-parse --short HEAD)

.PHONY: build push deploy run logs
build:
\tdocker build -t $(IMG) apps/$(SERVICE)

push:
\tgcloud auth configure-docker us-central1-docker.pkg.dev --quiet
\tdocker push $(IMG)

deploy:
\tgcloud run deploy $(SERVICE) \
\t  --image=$(IMG) --region=$(REGION) --no-allow-unauthenticated \
\t  --service-account=audio-prep-sa@$(PROJECT_ID).iam.gserviceaccount.com \
\t  --set-env-vars=PROJECT_ID=$(PROJECT_ID),REGION=global,OUTPUT_BUCKET=phi-output-encounters,OUTPUT_PREFIX=transcripts/,PREPPED_BUCKET=phi-inbound-audio-raw,PREPPED_PREFIX=prepped/,SPEECH_MODEL=medical_conversation

logs:
\tgcloud logs tail --region=$(REGION) --service=$(SERVICE)
