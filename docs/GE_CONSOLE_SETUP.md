# GE Admin Console — Required toggles for observability

These are **manual** steps a GE admin must do for the dashboard to capture all data.
**The Terraform module CANNOT do this — there is no API.**

## When to do this

After Terraform `apply` succeeds and the BQ dataset + sink are in place.

## Steps

1. Open Google Cloud Console → Search "Discovery Engine" or go to
   <https://console.cloud.google.com/gen-app-builder/engines>
2. Select your project + the engine (app) you want to observe
3. Click into the engine → **Configurations** tab (or "Settings" depending on UI version)
4. Find the **Observability** section
5. Toggle ON:

| Toggle | What it does | Impact if off |
|---|---|---|
| **Enable Feedback** | Records user thumbs-up/down on responses | Feedback events column will be empty |
| **Enable OpenTelemetry Instrumentation** | Generates trace IDs that link prompt → response | Conversations page can't pair them (all "no_response") |
| **Enable Prompt and Response Logging** | Writes `gen_ai.user.message` + `gen_ai.choice` logs | No prompt/response content in dashboard at all |

6. Click **Save**. Allow ~5 min for changes to take effect.

## Verify

After enabling, send a chat in the GE web UI. Then:

```bash
gcloud logging read \
  'logName=~"discoveryengine.googleapis.com.*gen_ai" AND timestamp>"-5m"' \
  --project=$PROJECT_ID --limit=3
```

Should return at least 1 `gen_ai.choice` entry.

## ⚠️ Cost impact

Enabling Prompt + Response logging dramatically increases log volume — prompts and responses
are stored verbatim. For a 1M-chat/month deployment expect:
- ~10 GB/month log ingestion → $0.50/month sink cost
- ~10 GB BQ storage → $0.20/month
- Plus per-query cost when dashboard reads

For very high-volume use, consider dropping low-value chunks (`finish_reason='UNSPECIFIED'`)
via sink filter, or partition the choice table by day with a 30-day retention policy.

## Privacy / PII

The `gen_ai.user.message` table contains **raw user prompts**. These may include:
- Internal document content (employees asking GE to summarize confidential docs)
- Customer / contract data
- Credentials accidentally pasted (we apply regex redaction but it's not bulletproof)

**Recommend**: layer Cloud DLP API for true PII scrubbing, restrict BQ dataset access
to a small group, and enable BQ audit logs for the dataset itself ("who saw the prompts").
