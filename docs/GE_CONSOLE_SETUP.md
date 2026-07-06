# GE Admin Console — Observability toggles

Two of the three toggles now have a public API and are flipped automatically
by `bootstrap.py`. Only "Enable Feedback" still requires a manual click.

## What flips automatically (as of 2026-07-06)

`bootstrap.py` runs `PATCH .../engines/{id}?updateMask=observabilityConfig`
against every engine in the project:

```json
{
  "observabilityConfig": {
    "observabilityEnabled": true,
    "sensitiveLoggingEnabled": true
  }
}
```

- `observabilityEnabled` ↔ **Enable OpenTelemetry Instrumentation** (generates
  trace IDs pairing prompt → response, and turns on `serviceTextReply` inline
  responses in `user_activity`)
- `sensitiveLoggingEnabled` ↔ **Enable Prompt and Response Logging** (writes
  raw prompt + response text to `gen_ai.user.message` and `gen_ai.choice`,
  plus populates `jsonPayload.serviceTextReply` in user_activity)

To skip this automation (e.g. if you want to leave some engines untouched):

```bash
SKIP_OBSERVABILITY=true make bootstrap PROJECT=…
```

Then flip the toggles manually per the "manual steps" section below.

## What still needs a manual click

| Toggle | What it does | Impact if off |
|---|---|---|
| **Enable Feedback** | Records user thumbs-up/down on responses | Feedback events column will be empty |

`Feedback` has no known API field yet — you have to click in the console.

## Manual steps (skip if automation succeeded)

1. Open Google Cloud Console → Search "Discovery Engine" or go to
   <https://console.cloud.google.com/gen-app-builder/engines>
2. Select your project + the engine (app) you want to observe
3. Click into the engine → **Configurations** tab (or "Settings" depending on UI version)
4. Find the **Observability** section
5. Toggle ON the ones you need (see table above)
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
