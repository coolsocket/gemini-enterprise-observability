# Runbook

Common operational tasks + troubleshooting for GE Observability.

## Restart service

```bash
# Local uvicorn
fuser -k 8011/tcp
cd /path/to/ge-observability-service
env -u GOOGLE_APPLICATION_CREDENTIALS \
  .venv/bin/uvicorn --app-dir apps/api main:app --host 127.0.0.1 --port 8011 &

# Cloud Run
gcloud run services update ge-observability --region us-central1 --no-traffic
gcloud run services update-traffic ge-observability --region us-central1 --to-latest
```

## Refresh snapshots

```bash
# Via dashboard UI: click ⟳ button in header
# Via API:
curl -s -X POST -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://<cloud-run-url>/api/refresh | jq

# Via BQ directly:
PROJECT=<your-project> bq query --use_legacy_sql=false \
  "CREATE OR REPLACE TABLE \`$PROJECT.ge_observability.s_user_persona\` AS \
   SELECT * FROM \`$PROJECT.ge_observability.v_user_persona\`"
```

## Re-deploy views after SQL change

```bash
# Edit infra/sql_templates/views.sql.tmpl
PROJECT=<your-project> DATASET=ge_observability \
  python3 infra/scripts/apply_views.py
```

## Simulate users (e.g. for demos)

Already-created sim SAs: `<sim-prefix>-alice` ... `<sim-prefix>-henry`. To add more:

```bash
PROJ=<your-project>
TOKEN=$(gcloud auth print-access-token)
for NAME in ivy jack kate liam; do
  curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"accountId\":\"<sim-prefix>-$NAME\"}" \
    "https://iam.googleapis.com/v1/projects/$PROJ/serviceAccounts"
done
# Then run /tmp/sim_chat.sh after granting roles/discoveryengine.editor + iam.serviceAccountTokenCreator
```

## Troubleshooting

### Dashboard 503 / 502

- Check Cloud Run logs: `gcloud run services logs read ge-observability --region us-central1 --limit 50`
- Check uvicorn locally: `tail -50 /tmp/ge-uvicorn.log`
- Most common: `GOOGLE_APPLICATION_CREDENTIALS` env var pointing at expired user creds.
  Fix: `unset GOOGLE_APPLICATION_CREDENTIALS` before launching uvicorn.

### `/api/v/<view>` returns 500

- Likely a view definition refers to a missing column.
  - Check uvicorn log for `Unrecognized name: X`
  - Re-apply views: `python3 infra/scripts/apply_views.py`

### Snapshot refresh failed

- Check `SELECT * FROM ge_observability.snapshot_meta ORDER BY refreshed_at DESC LIMIT 20`
- See which `snapshot_name` last failed (look for gaps)
- BQ Scheduled Query status: Cloud Console → BigQuery → Scheduled Queries
- Manual rerun: trigger from dashboard UI (Settings → "立即刷新全部")

### No new logs landing in BQ

- Check sink filter: `gcloud logging sinks describe ge-observability-unified --project=$PROJ`
- Check sink writer has dataset access:
  `bq show --format=prettyjson <your-project>:ge_observability | jq '.access[] | select(.role=="WRITER")'`
- Wait 1-5min for first events to appear after sink creation.

### `Conversations` page shows all "无响应"

- Expected for users chatting via GE Console UI (v1main path doesn't emit gen_ai.choice)
- Only `v1alpha` REST calls produce paired prompt+response
- See README "Documented data limitations" #2

### Multimodal data missing

- Expected — GE `streamAssist` API rejects `inlineData` parts (see README #1)
- File uploads tracked separately via `session_files` count in `v_data_access_summary`

## Cost control

Estimated BQ costs (US region, on-demand pricing):

| Item | Volume | Approx monthly cost |
|---|---|---|
| Logs Router → BQ ingestion | depends on chat volume | $0.05/GB sinked |
| BQ storage | 5 raw tables + 13 snapshots | $20/TB/month |
| Scheduled Query (4 runs/day) | ~10 MB scanned per run | <$1/month |
| On-demand query (dashboard) | depends on traffic | <$5/month at 100 users |

For high-volume deployments (>1M GE chats/month), consider:
- BQ slot reservation instead of on-demand
- Partition snapshot tables by day (already on `timestamp` field)
- Drop streaming chunks more aggressively (keep only `gen_ai.choice` `STOP` rows)

## Revoke access

```bash
# Remove a user from dashboard access
gcloud run services remove-iam-policy-binding ge-observability \
  --region us-central1 --project=$PROJ \
  --member="user:alice@example.com" \
  --role="roles/run.invoker"

# Disable dashboard SA (e.g. on rotation)
gcloud iam service-accounts disable ge-observability-sa@$PROJ.iam.gserviceaccount.com
```

## Tear down

```bash
# Stop accepting traffic
gcloud run services delete ge-observability --region us-central1

# Remove Scheduled Query
bq ls --transfer_config --transfer_location=us | grep "GE Observability" | awk '{print $1}' | \
  xargs -I {} bq rm --transfer_config {}

# Drop BQ dataset (DESTRUCTIVE)
bq rm -r -f <your-project>:ge_observability

# Remove sink
gcloud logging sinks delete ge-observability-unified

# Or use Terraform:
terraform -chdir=terraform destroy
```
