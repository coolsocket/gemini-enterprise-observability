.PHONY: install web-install web-build api-run serve dev tunnel-info \
        tf-init tf-plan tf-apply views bootstrap image deploy all clean

PY ?= python3
VENV := .venv
PORT ?= 8000

# ============================================================
# Local development
# ============================================================
install: web-install
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r apps/api/requirements.txt

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
# Required: PROJECT=<id>  REGION=<region>  IMAGE=<container_image>
# ============================================================
PROJECT ?=
REGION ?= us-central1
DATASET ?= ge_observability
IMAGE ?= gcr.io/$(PROJECT)/ge-observability:latest

check-project:
	@if [ -z "$(PROJECT)" ]; then echo "ERROR: PROJECT=<gcp-project-id> required"; exit 1; fi

# Step 1: terraform plan (preview)
tf-init: check-project
	cd terraform && terraform init
tf-plan: tf-init
	cd terraform && terraform plan -var "project_id=$(PROJECT)" -var "region=$(REGION)" \
	  -var "dataset_id=$(DATASET)" -var "container_image=$(IMAGE)"

# Step 2: terraform apply (creates dataset, sink, audit-config, SA, IAM, optionally Cloud Run)
tf-apply: tf-init
	cd terraform && terraform apply -auto-approve \
	  -var "project_id=$(PROJECT)" -var "region=$(REGION)" \
	  -var "dataset_id=$(DATASET)" -var "container_image=$(IMAGE)"

# Step 3: build container image and push to GCR
image: check-project
	gcloud builds submit --project=$(PROJECT) --tag=$(IMAGE) .

# Step 4: apply BQ views (renders {{PROJECT}}/{{DATASET}} placeholders)
# Uses venv python if available, otherwise system python3
views: check-project
	@if [ -x $(VENV)/bin/python3 ]; then PY=$(VENV)/bin/python3; else PY=$(PY); fi; \
	PROJECT=$(PROJECT) DATASET=$(DATASET) $$PY infra/scripts/apply_views.py

# Step 5: ingest engine_metadata + resources_alive + seed quota_config
bootstrap: check-project
	@if [ -x $(VENV)/bin/python3 ]; then PY=$(VENV)/bin/python3; else PY=$(PY); fi; \
	PROJECT=$(PROJECT) DATASET=$(DATASET) $$PY infra/scripts/bootstrap.py

# Step 6: deploy = all of the above in order (after GE admin toggles done)
deploy: tf-apply image views bootstrap
	@echo ""
	@echo "✓ Deployment complete. Service URL:"
	@cd terraform && terraform output -raw service_url
	@echo ""
	@echo "Next: configure IAP via Cloud Console if you want SSO,"
	@echo "and add invokers via 'iap_invokers' in terraform.tfvars."

# Full first-time install: enable APIs, terraform, build image, views, bootstrap
all: install deploy
	@echo "All done."
