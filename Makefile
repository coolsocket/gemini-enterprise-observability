.PHONY: install py-deps web-install web-build api-run serve dev tunnel-info \
        tf-init tf-plan tf-apply tf-import-orphans preflight views bootstrap image \
        deploy-infra deploy-views deploy resume all clean

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

# main.py reads BQ_PROJECT/BQ_DATASET/SIM_PREFIX at import time — need to
# thread them into uvicorn's env, not just Make's. `make serve PROJECT=foo`
# without the env-var prefix silently drops PROJECT and fails at import.
api-run: check-project
	. $(VENV)/bin/activate && cd apps/api && \
	BQ_PROJECT=$(PROJECT) BQ_DATASET=$(DATASET) SIM_PREFIX=$(SIM_PREFIX) \
	  uvicorn main:app --host 127.0.0.1 --port $(PORT) --reload

serve: check-project web-build
	. $(VENV)/bin/activate && cd apps/api && \
	BQ_PROJECT=$(PROJECT) BQ_DATASET=$(DATASET) SIM_PREFIX=$(SIM_PREFIX) \
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

# Prefix stripped from actor emails at query time (see infra/scripts/apply_views.py).
# Default 'sim-' matches nothing normally; override if your seed SAs use another prefix.
SIM_PREFIX ?= sim-

# BigQuery dataset location — separate from REGION (which is for Cloud Run +
# Artifact Registry). Default is the US multi-region for maximum availability.
# Common single-regions: `asia-southeast1` (Singapore), `asia-east1` (Taiwan),
# `europe-west1` (Belgium), `us-central1`. Data-residency laws usually want
# a single region; free-tier work can stay on the `US` multi-region.
# Cannot be changed after the dataset is created — pick once, live with it.
BQ_LOCATION ?= US

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
	  -var "dataset_id=$(DATASET)" -var "bq_location=$(BQ_LOCATION)" \
	  -var "container_image=$(IMAGE)" -var "ar_repo=$(AR_REPO)"

# Step 2: terraform apply (creates dataset, sink, audit-config, SA, IAM,
# Artifact Registry repo, and optionally Cloud Run)
tf-apply: tf-init
	cd terraform && terraform apply -auto-approve \
	  -var "project_id=$(PROJECT)" -var "region=$(REGION)" \
	  -var "dataset_id=$(DATASET)" -var "bq_location=$(BQ_LOCATION)" \
	  -var "container_image=$(IMAGE)" -var "ar_repo=$(AR_REPO)"

# Preflight: reports what's already in the target project (dataset, SA, sink,
# AR repo, audit config for discoveryengine) so the operator knows whether
# they'll get 409s or whether the audit-config change will overwrite existing
# exemptions. Interactive by default; set CONFIRM=y to auto-accept in scripts.
preflight: check-project
	PROJECT=$(PROJECT) DATASET=$(DATASET) REGION=$(REGION) AR_REPO=$(AR_REPO) \
	  bash infra/scripts/preflight.sh

# Recover from a partial/failed first `tf-apply` where resources leaked into
# GCP but never made it into terraform state, causing all subsequent applies
# to fail with `Error 409: Already Exists`. Idempotent — safe to re-run.
tf-import-orphans: check-project tf-init
	PROJECT=$(PROJECT) DATASET=$(DATASET) REGION=$(REGION) AR_REPO=$(AR_REPO) \
	  bash infra/scripts/import_orphans.sh

# Step 3: build container image and push to Artifact Registry.
# `SKIP_IMAGE=true` skips the Cloud Build submit — useful when you know the
# image is already up to date (e.g. re-running `deploy-infra` after just a
# terraform tweak). Cloud Build takes 1-3 min and re-building an unchanged
# image is the slowest wasted step in the chain.
image: check-project
	@if [ "$(SKIP_IMAGE)" = "true" ]; then \
	  echo "→ SKIP_IMAGE=true — not rebuilding image ($(IMAGE))"; \
	else \
	  gcloud builds submit --project=$(PROJECT) --tag=$(IMAGE) . ; \
	fi

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
deploy-infra: py-deps preflight tf-apply image bootstrap
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

# One-command recovery from a failed views apply. Auto-detects the existing
# dataset's actual BQ_LOCATION from GCP (so preflight's region-mismatch gate
# doesn't trip on state that already exists) and re-runs apply_views.py
# idempotently. Does NOT touch git — pull upstream fixes yourself first if
# you want the latest SQL. Safe to re-run.
resume: check-project py-deps
	@echo "→ Detecting existing dataset location on GCP..."
	@detected_loc=$$(bq --project_id=$(PROJECT) show --format=json $(DATASET) 2>/dev/null | \
	    python3 -c "import json,sys; print(json.load(sys.stdin).get('location','') or '')" 2>/dev/null); \
	  if [ -n "$$detected_loc" ]; then \
	    echo "  Dataset '$(DATASET)' exists at BQ_LOCATION=$$detected_loc — using that."; \
	    export BQ_LOCATION="$$detected_loc"; \
	  else \
	    echo "  Dataset '$(DATASET)' does not exist — using BQ_LOCATION=$(BQ_LOCATION)."; \
	  fi; \
	  BQ_LOCATION=$${BQ_LOCATION:-$(BQ_LOCATION)} PROJECT=$(PROJECT) DATASET=$(DATASET) \
	    $(VENV)/bin/python3 infra/scripts/apply_views.py
	@echo ""
	@echo "✓ Resume complete. Check the output above — 'applied N/21' should be 21"
	@echo "  unless some views are still waiting for log-sink tables (need more"
	@echo "  GE traffic + a re-run of 'make resume' or 'make deploy-views')."

# Full first-time install: install web+py deps, then the two-phase deploy.
all: install deploy-infra
	@echo ""
	@echo "Web+py deps installed and Phase A deploy done. Read the message above"
	@echo "for the manual GE Console step before running 'make deploy-views'."
