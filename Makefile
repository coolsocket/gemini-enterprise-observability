.PHONY: install py-deps web-install web-build api-run serve dev tunnel-info \
        tf-init tf-plan tf-apply tf-import-orphans views bootstrap image \
        deploy-infra deploy-views deploy all clean

PY ?= python3
VENV := .venv
PORT ?= 8000

# ============================================================
# Local development
# ============================================================
install: web-install py-deps

# Python venv only (used by deploy chain; no node needed)
py-deps:
	@if [ ! -x $(VENV)/bin/python3 ]; then \
	  echo "→ creating venv + installing python deps"; \
	  $(PY) -m venv $(VENV) && $(VENV)/bin/pip install -q -r apps/api/requirements.txt; \
	fi

web-install:
	cd apps/web && npm install --silent --no-audit --no-fund

web-build:
	cd apps/web && npm run build

api-run:
	. $(VENV)/bin/activate && cd apps/api && \
	uvicorn main:app --host 127.0.0.1 --port $(PORT) --reload

serve: web-build
	. $(VENV)/bin/activate && cd apps/api && \
	uvicorn main:app --host 127.0.0.1 --port $(PORT)

dev:
	@echo "Run in two terminals:"
	@echo "  1) make api-run    (FastAPI on http://127.0.0.1:8000)"
	@echo "  2) cd apps/web && npm run dev  (Vite on http://127.0.0.1:5173)"

tunnel-info:
	@echo "From your laptop:"
	@echo "  ssh -L $(PORT):127.0.0.1:$(PORT) <this-host>"
	@echo "Then open http://localhost:$(PORT)/"

clean:
	rm -rf $(VENV) apps/web/node_modules apps/web/dist

# ============================================================
# Deployment to a fresh GCP project
# Required: PROJECT=<id>  REGION=<region>
# Optional: DATASET=<name>  IMAGE=<full-image-tag>  AR_REPO=<name>
# ============================================================
PROJECT ?=
REGION ?= us-central1
DATASET ?= ge_observability

# Artifact Registry (not the deprecated gcr.io). Repository is created by
# terraform (google_artifact_registry_repository.dashboard). Image tag format:
# <region>-docker.pkg.dev/<project>/<repo>/dashboard:latest
AR_REPO ?= ge-observability
IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT)/$(AR_REPO)/dashboard:latest

check-project:
	@if [ -z "$(PROJECT)" ]; then echo "ERROR: PROJECT=<gcp-project-id> required"; exit 1; fi

# Step 1: terraform plan (preview)
tf-init: check-project
	cd terraform && terraform init
tf-plan: tf-init
	cd terraform && terraform plan -var "project_id=$(PROJECT)" -var "region=$(REGION)" \
	  -var "dataset_id=$(DATASET)" -var "container_image=$(IMAGE)" -var "ar_repo=$(AR_REPO)"

# Step 2: terraform apply (creates dataset, sink, audit-config, SA, IAM,
# Artifact Registry repo, and optionally Cloud Run)
tf-apply: tf-init
	cd terraform && terraform apply -auto-approve \
	  -var "project_id=$(PROJECT)" -var "region=$(REGION)" \
	  -var "dataset_id=$(DATASET)" -var "container_image=$(IMAGE)" -var "ar_repo=$(AR_REPO)"

# Recover from a partial/failed first `tf-apply` where resources leaked into
# GCP but never made it into terraform state, causing all subsequent applies
# to fail with `Error 409: Already Exists`. Idempotent — safe to re-run.
tf-import-orphans: check-project tf-init
	PROJECT=$(PROJECT) DATASET=$(DATASET) REGION=$(REGION) AR_REPO=$(AR_REPO) \
	  bash infra/scripts/import_orphans.sh

# Step 3: build container image and push to Artifact Registry
image: check-project
	gcloud builds submit --project=$(PROJECT) --tag=$(IMAGE) .

# Step 4: apply BQ views (renders {{PROJECT}}/{{DATASET}}/{{SIM_PATTERN}}/
# {{SIM_PREFIX}} placeholders). Idempotent — safe to re-run; missing log-sink
# tables (which only appear after logs first flow) are reported as "waiting"
# so you can run this again after enabling GE Console toggles + a bit of
# traffic.
views: check-project py-deps
	PROJECT=$(PROJECT) DATASET=$(DATASET) $(VENV)/bin/python3 infra/scripts/apply_views.py

# Step 5: ingest engine_metadata + resources_alive + seed quota_config
bootstrap: check-project py-deps
	PROJECT=$(PROJECT) DATASET=$(DATASET) $(VENV)/bin/python3 infra/scripts/bootstrap.py

# ---------- Two-phase deploy (recommended for fresh projects) ----------
# Phase A: everything that can succeed before GE has emitted any logs.
deploy-infra: py-deps tf-apply image bootstrap
	@echo ""
	@echo "✓ Phase A done. Infrastructure + image + metadata ready."
	@echo ""
	@echo "NEXT (manual):"
	@echo "  1. Open GE Admin Console for each engine and enable:"
	@echo "       - OpenTelemetry Instrumentation"
	@echo "       - Prompt & Response Logging"
	@echo "       - Feedback (optional)"
	@echo "  2. Generate some traffic (chat / deep research / notebook click)."
	@echo "  3. Wait ~2-5 min for logs to land in BQ, then:"
	@echo "       make deploy-views PROJECT=$(PROJECT) DATASET=$(DATASET)"

# Phase B: apply views once GE has emitted enough logs for BigQuery to have
# created the sink-target tables (cloudaudit_googleapis_com_data_access, etc).
deploy-views: py-deps views
	@echo ""
	@echo "✓ Phase B done. Views applied."
	@echo ""
	@echo "Optional next: enable deploy_cloud_run in terraform.tfvars + re-apply,"
	@echo "or run 'make serve' to preview the dashboard locally."

# Legacy one-shot alias — kept for repeat deploys where logs are already flowing.
# On a truly fresh project prefer deploy-infra then (after logs) deploy-views.
deploy: py-deps tf-apply image bootstrap views
	@echo ""
	@echo "✓ Deploy complete."

# Full first-time install: install web+py deps, then the two-phase deploy.
all: install deploy-infra
	@echo ""
	@echo "Web+py deps installed and Phase A deploy done. Read the message above"
	@echo "for the manual GE Console step before running 'make deploy-views'."
