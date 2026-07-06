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

# Probe GE API: chat / image / video via SA impersonation.
# Records raw responses to results/<name>.json for downstream analysis.
set -uo pipefail   # NOT -e — we want each probe to run even if others fail
cd "$(dirname "$0")"

# Configure these for your project before running
PROJECT="${GE_PROJECT:-PROJECT_ID}"
SA="${GE_SA:-test-sa@${PROJECT}.iam.gserviceaccount.com}"
ENGINE="${GE_ENGINE:-YOUR_ENGINE_ID}"
BASE="https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT}/locations/global/collections/default_collection/engines/${ENGINE}"

mkdir -p results

echo "==> Getting SA impersonation token..."
TOKEN=$(gcloud auth print-access-token --impersonate-service-account="$SA" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  echo "FAIL: could not impersonate $SA"
  echo "Make sure your user has roles/iam.serviceAccountTokenCreator on the SA"
  exit 1
fi
echo "OK ($(echo -n "$TOKEN" | wc -c) chars)"

hdr=(-H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json")

# --- Probe 1: StreamAssist plain chat ---
echo ""
echo "==> [1/5] StreamAssist — plain chat"
cat > /tmp/req_chat.json <<'JSON'
{
  "query": { "text": "What is 2+2? Reply with just the number." },
  "session": "-"
}
JSON
curl -sS -X POST "${hdr[@]}" \
  "${BASE}/assistants/default_assistant:streamAssist" \
  -d @/tmp/req_chat.json > results/01_chat.json
head -c 500 results/01_chat.json ; echo ""

# --- Probe 2: StreamAssist asking for image ---
echo ""
echo "==> [2/5] StreamAssist — asking for an image"
cat > /tmp/req_img.json <<'JSON'
{
  "query": { "text": "Generate an image of a frog wearing a top hat, cartoon style" },
  "session": "-"
}
JSON
curl -sS -X POST "${hdr[@]}" \
  "${BASE}/assistants/default_assistant:streamAssist" \
  -d @/tmp/req_img.json > results/02_image_via_chat.json
head -c 800 results/02_image_via_chat.json ; echo ""

# --- Probe 3: StreamAssist asking for video ---
echo ""
echo "==> [3/5] StreamAssist — asking for a video"
cat > /tmp/req_vid.json <<'JSON'
{
  "query": { "text": "Generate a 5-second video of ocean waves at sunset" },
  "session": "-"
}
JSON
curl -sS -X POST "${hdr[@]}" \
  "${BASE}/assistants/default_assistant:streamAssist" \
  -d @/tmp/req_vid.json > results/03_video_via_chat.json
head -c 800 results/03_video_via_chat.json ; echo ""

# --- Probe 4: AsyncAssist (Deep Research) ---
echo ""
echo "==> [4/5] AsyncAssist — Deep Research submit"
cat > /tmp/req_dr.json <<'JSON'
{
  "query": { "text": "Research the current state of retrieval-augmented generation in 2026." },
  "session": "-"
}
JSON
curl -sS -X POST "${hdr[@]}" \
  "${BASE}/assistants/default_assistant:asyncAssist" \
  -d @/tmp/req_dr.json > results/04_deep_research.json
head -c 800 results/04_deep_research.json ; echo ""

# --- Probe 5: Direct Vertex Imagen call (bypass GE) ---
echo ""
echo "==> [5/5] Direct Vertex Imagen (bypass GE)"
IMAGEN_ENDPOINT="https://us-central1-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/us-central1/publishers/google/models/imagegeneration:predict"
cat > /tmp/req_imagen.json <<'JSON'
{
  "instances": [{ "prompt": "A frog wearing a top hat, cartoon style" }],
  "parameters": { "sampleCount": 1 }
}
JSON
curl -sS -X POST "${hdr[@]}" \
  "$IMAGEN_ENDPOINT" \
  -d @/tmp/req_imagen.json > results/05_vertex_imagen.json
head -c 500 results/05_vertex_imagen.json ; echo ""

echo ""
echo "==> Done. See results/ for full outputs, then run: python3 analyze.py"
