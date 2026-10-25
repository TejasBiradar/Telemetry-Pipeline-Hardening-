#!/bin/sh
# Onboard user_behavior, confirm stages/guarantees, set MinIO store, upload sample dumps.
set -eu

API_URL="${API_URL:-http://api:8000}"
SOURCE="${SOURCE:-/app/pipelines/user_behavior/src}"
PREFIX="${PREFIX:-demo/user_behavior/outputs}"

echo "Waiting for API at ${API_URL}..."
i=0
until curl -sf "${API_URL}/health" >/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "API did not become healthy" >&2
    exit 1
  fi
  sleep 2
done

echo "Onboarding pipeline from ${SOURCE}..."
ONBOARD=$(curl -sf -X POST "${API_URL}/pipelines/code-onboard" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Demo User Behavior\",\"source_path\":\"${SOURCE}\",\"entry\":\"run.run\",\"select\":true}")
PID=$(printf '%s' "$ONBOARD" | python -c "import sys,json; print(json.load(sys.stdin)['pipeline_id'])")
export PIPELINE_ID="$PID"
echo "pipeline_id=${PID}"

echo "Confirming stages..."
curl -sf -X PUT "${API_URL}/pipelines/${PID}/stages/decisions" \
  -H "Content-Type: application/json" \
  -d '{"decisions":{"ingest":"confirmed","filter_sessions":"confirmed","aggregate":"confirmed"}}' \
  >/dev/null

echo "Confirming guarantees (all pending → confirmed)..."
python - <<'PY'
import json
import os
import urllib.parse
import urllib.request

api = os.environ.get("API_URL", "http://api:8000")
pid = os.environ["PIPELINE_ID"]
meta = json.load(urllib.request.urlopen(f"{api}/pipelines/{pid}/code-onboard"))
for fid, status in meta.get("guarantee_status", {}).items():
    if status != "pending":
        continue
    req = urllib.request.Request(
        f"{api}/pipelines/{pid}/guarantees/{urllib.parse.quote(fid, safe='')}/decision",
        data=json.dumps({"status": "confirmed"}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req)
print("guarantees confirmed")
PY

echo "Setting MinIO output store..."
curl -sf -X PUT "${API_URL}/pipelines/${PID}/output-store" \
  -H "Content-Type: application/json" \
  -d "{\"endpoint\":\"http://${MINIO_ENDPOINT:-minio:9000}\",\"bucket\":\"demo\",\"prefix\":\"${PREFIX}\",\"secure\":false}" \
  >/dev/null

echo "Uploading sample stage dumps..."
python /app/docker/seed_minio.py --pipeline-id "$PID" --prefix "$PREFIX"

echo "Done. pipeline_id=${PID}"
echo "Watch agent logs, then: curl ${API_URL}/pipelines/${PID}/agent/results/latest"
