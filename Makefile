PROJECT_ID ?= automations-n8n-463018
RUN_REGION ?= us-central1
SERVICE ?= medical-transcribe

.PHONY: logs tail deploy trigger
logs:
\tgcloud run services logs read $(SERVICE) --region=$(RUN_REGION) --limit=200

tail:
\tgcloud beta logging tail \
\t  --project=$(PROJECT_ID) \
\t  --filter='resource.type="cloud_run_revision" AND resource.labels.service_name="$(SERVICE)" AND resource.labels.location="$(RUN_REGION)"'
