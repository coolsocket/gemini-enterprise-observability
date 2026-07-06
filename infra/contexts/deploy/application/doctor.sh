#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Non-destructive environment check. Reports each dependency + its install
# hint if missing, plus useful state (venv, node_modules, ADC, .env).
# Always exits 0 — informational only. Read by `make doctor`.

set -uo pipefail
cd "$(dirname "$0")/../../../.."

if [ -t 1 ]; then
  G=$(tput setaf 2); Y=$(tput setaf 3); R=$(tput setaf 1); B=$(tput bold); D=$(tput dim); N=$(tput sgr0)
else
  G=""; Y=""; R=""; B=""; D=""; N=""
fi

ok()   { echo "  ${G}✓${N} $1"; }
warn() { echo "  ${Y}⚠${N} $1"; [ -n "${2:-}" ] && echo "     ${D}→ $2${N}"; }
bad()  { echo "  ${R}✗${N} $1"; [ -n "${2:-}" ] && echo "     ${D}→ $2${N}"; }

echo "${B}==> Toolchain${N}"

# --- Python ---
if command -v python3 >/dev/null 2>&1; then
  py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
  py_major=$(python3 -c 'import sys; print(sys.version_info.major)')
  py_minor=$(python3 -c 'import sys; print(sys.version_info.minor)')
  if [ "$py_major" -ge 3 ] && [ "$py_minor" -ge 9 ]; then
    ok "Python ${py_ver} (need ≥3.9)"
  else
    bad "Python ${py_ver} is too old (need ≥3.9)" \
        "install: pyenv install 3.11 && pyenv local 3.11  (or use system 3.11+)"
  fi
else
  bad "python3 not found" "install: https://www.python.org/downloads/  or  brew install python@3.11"
fi

# --- Node ---
if command -v node >/dev/null 2>&1; then
  node_ver=$(node --version)             # e.g. v18.20.4
  node_major=$(echo "$node_ver" | sed -E 's/^v([0-9]+).*/\1/')
  if [ "$node_major" -ge 18 ]; then
    ok "Node ${node_ver} (need ≥18 for Vite 5)"
  else
    bad "Node ${node_ver} is too old (need ≥18)" \
        "install: brew install node@20  or  https://nodejs.org/"
  fi
else
  warn "node not found" "install: brew install node@20  (only required for web build)"
fi

# --- gcloud ---
if command -v gcloud >/dev/null 2>&1; then
  gcloud_ver=$(gcloud version 2>/dev/null | head -1 | awk '{print $NF}')
  ok "gcloud ${gcloud_ver}"
else
  bad "gcloud not found" "install: brew install --cask google-cloud-sdk  or  https://cloud.google.com/sdk/docs/install"
fi

# --- terraform ---
if command -v terraform >/dev/null 2>&1; then
  tf_ver=$(terraform version | head -1 | awk '{print $NF}')
  ok "terraform ${tf_ver}"
else
  bad "terraform not found" "install: brew install terraform  or  https://developer.hashicorp.com/terraform/install"
fi

# --- make ---
if command -v make >/dev/null 2>&1; then
  ok "make $(make --version | head -1 | awk '{print $NF}')"
else
  bad "make not found (very unusual — comes with most OSes)"
fi

echo ""
echo "${B}==> Authentication${N}"

# --- gcloud user login ---
# Set DOCTOR_AUTOAUTH=n to skip the auto-spawn prompts (e.g. CI). Default is
# interactive: if creds are missing, prompt Y/n and spawn the flow with
# stdio inheritance so the browser OAuth loop completes cleanly.
if command -v gcloud >/dev/null 2>&1; then
  account=$(gcloud config get-value account 2>/dev/null || true)
  if [ -n "$account" ] && [ "$account" != "(unset)" ]; then
    ok "gcloud active account: ${account}"
  else
    bad "gcloud not authed"
    if [ -t 0 ] && [ "${DOCTOR_AUTOAUTH:-y}" != "n" ]; then
      read -r -p "     Run \`gcloud auth login\` now? [Y/n] " reply
      if [ "$reply" != "n" ] && [ "$reply" != "N" ]; then
        gcloud auth login
      fi
    else
      echo "     ${D}→ run: gcloud auth login${N}"
    fi
  fi

  # --- ADC (main.py + bootstrap.py use google.auth.default) ---
  adc_path="$HOME/.config/gcloud/application_default_credentials.json"
  if [ -f "$adc_path" ] || [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
    if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
      ok "ADC via GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS"
    else
      ok "ADC via ~/.config/gcloud/application_default_credentials.json"
    fi
  else
    bad "ADC not configured (Python scripts + FastAPI need this)"
    if [ -t 0 ] && [ "${DOCTOR_AUTOAUTH:-y}" != "n" ]; then
      read -r -p "     Run \`gcloud auth application-default login\` now? [Y/n] " reply
      if [ "$reply" != "n" ] && [ "$reply" != "N" ]; then
        gcloud auth application-default login
      fi
    else
      echo "     ${D}→ run: gcloud auth application-default login${N}"
    fi
  fi
fi

echo ""
echo "${B}==> Project state${N}"

# --- venv ---
if [ -x .venv/bin/python3 ]; then
  venv_py=$(.venv/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
  ok ".venv exists (Python ${venv_py})"
  # Are our deps installed?
  if .venv/bin/python3 -c 'import fastapi, uvicorn; import google.cloud.bigquery' 2>/dev/null; then
    ok ".venv has fastapi + uvicorn + google-cloud-bigquery"
  else
    warn ".venv missing some deps" "run: make py-deps  (or: .venv/bin/pip install -r apps/api/requirements.txt)"
  fi
else
  warn ".venv not created yet" "run: make install  (or: make py-deps)"
fi

# --- web deps ---
if [ -d apps/web/node_modules ]; then
  ok "apps/web/node_modules present"
else
  warn "apps/web/node_modules missing" "run: make install  (or: cd apps/web && npm install)"
fi

# --- .env ---
if [ -f .env ]; then
  ok ".env file present (Makefile will include it)"
elif [ -f .env.example ]; then
  warn ".env not created" "run: cp .env.example .env && \$EDITOR .env"
fi

echo ""
echo "${B}==> Summary${N}"
echo "This report is informational only — nothing was changed."
echo "Follow the ${D}→${N} hints above for anything that's ${R}✗${N} or ${Y}⚠${N}."
exit 0
