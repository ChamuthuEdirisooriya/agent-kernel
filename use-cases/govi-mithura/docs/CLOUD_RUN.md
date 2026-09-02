# Optional permanent Google Cloud Run deployment

This deployment keeps the Meta callback stable without requiring a laptop or temporary tunnel to
remain online, and runs the same `server.py` entry point and public `govi_mithura` graph as local
development.

The example below deploys a `govi-mithura` service in `asia-south1`. Cloud Run assigns a stable
HTTPS service URL after deployment; append `/health` for the health check and
`/whatsapp/webhook` for the Meta callback. The service scales from zero to one instance, uses one
vCPU and 1 GiB memory, and allows four concurrent requests. The 300-second Cloud Run timeout is an
outer request limit; the application applies its own shorter timeout to each model attempt.

## Runtime design

- Cloud Run builds the checked-in `Dockerfile` from the use-case directory.
- A dedicated runtime service account has Vertex AI, Firestore, logging, and per-secret access.
- Meta verify token, access token, app secret, and phone-number ID are separate Secret Manager
  secrets. No credential is baked into the image or source upload.
- Agent Kernel sessions use the `govi-mithura-sessions` Firestore collection in the default
  database. The app stamps a seven-day `expiry_time`, and the collection has a TTL policy on that
  field.
- `session_compat.py` excludes LangGraph's process-local serializer callback from Agent Kernel
  0.8.1's pickled session value and reconstructs it when loading. The stored checkpoint data is
  unchanged; remove this narrow compatibility adapter after the upstream checkpointer becomes
  directly pickle-serializable again.
- This deployment example uses Vertex AI. Local development may use the primary OpenAI-compatible
  setup, Google AI Studio, or Vertex AI independently. The example selects `gemini-3.6-flash`
  because it produced the most consistent latency for this application's multi-call tool flow in
  development testing; serving latency remains workload- and capacity-dependent.

The direct Cloud Run deployment intentionally omits API Gateway, a VPC connector, and Cloud NAT:
Meta needs a public raw-body webhook and Cloud Run already supplies managed HTTPS. These resources
can be added later only if a concrete networking or gateway requirement appears.

## Required configuration

Create or select a billing-enabled Google Cloud project, a Firestore Native database, and a
dedicated runtime service account. Enable Cloud Run, Cloud Build, Artifact Registry, Secret
Manager, Firestore, and Vertex AI. The runtime uses these non-secret variables:

```text
LLM_PROVIDER=google_vertex
LLM_MODEL=gemini-3.6-flash
LLM_THINKING_LEVEL=low
LLM_REQUEST_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=global
AK_SESSION__TYPE=firestore
AK_SESSION__FIRESTORE__COLLECTION_NAME=govi-mithura-sessions
AK_SESSION__FIRESTORE__PROJECT_ID=YOUR_PROJECT_ID
AK_SESSION__FIRESTORE__DATABASE_ID=(default)
AK_SESSION__FIRESTORE__TTL=604800
AK_WHATSAPP__API_VERSION=v25.0
```

Map the following runtime variables to four Secret Manager secrets rather than plain environment
values:

```text
AK_WHATSAPP__VERIFY_TOKEN
AK_WHATSAPP__ACCESS_TOKEN
AK_WHATSAPP__APP_SECRET
AK_WHATSAPP__PHONE_NUMBER_ID
```

Grant the Cloud Build identity only source-object read, deployment-repository write, and log-write
permissions needed by a source deployment. Avoid a broad builder role when narrower bucket and
repository grants work.

## Deploy and accept

Run the deployment from this directory after replacing the project, service-account, and four
Secret Manager placeholders. The command contains secret names only; never substitute secret
values into it:

```bash
gcloud run deploy govi-mithura \
  --project=YOUR_PROJECT_ID \
  --region=asia-south1 \
  --source=. \
  --service-account=YOUR_RUNTIME_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min=0 \
  --max=1 \
  --cpu=1 \
  --memory=1Gi \
  --concurrency=4 \
  --timeout=300s \
  --set-env-vars="LLM_PROVIDER=google_vertex,LLM_MODEL=gemini-3.6-flash,LLM_THINKING_LEVEL=low,LLM_REQUEST_TIMEOUT_SECONDS=30,LLM_MAX_RETRIES=1,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,AK_SESSION__TYPE=firestore,AK_SESSION__FIRESTORE__COLLECTION_NAME=govi-mithura-sessions,AK_SESSION__FIRESTORE__PROJECT_ID=YOUR_PROJECT_ID,AK_SESSION__FIRESTORE__DATABASE_ID=(default),AK_SESSION__FIRESTORE__TTL=604800,AK_WHATSAPP__API_VERSION=v25.0" \
  --set-secrets="AK_WHATSAPP__VERIFY_TOKEN=YOUR_VERIFY_TOKEN_SECRET:latest,AK_WHATSAPP__ACCESS_TOKEN=YOUR_ACCESS_TOKEN_SECRET:latest,AK_WHATSAPP__APP_SECRET=YOUR_APP_SECRET_SECRET:latest,AK_WHATSAPP__PHONE_NUMBER_ID=YOUR_PHONE_NUMBER_ID_SECRET:latest"
```

Minimum instances remain at zero, maximum instances at one, and unauthenticated access is required
because Meta must reach the webhook. A redeploy creates a revision but preserves the stable service
URL.

After deployment:

1. Copy the service URL printed by `gcloud run deploy` and confirm
   `GET https://YOUR_CLOUD_RUN_SERVICE_URL/health` returns HTTP 200.
2. In Meta, set the callback URL to
   `https://YOUR_CLOUD_RUN_SERVICE_URL/whatsapp/webhook`, enter the matching verify token, and
   subscribe to `messages`.
3. Send an onboarding message with a town or village, then a follow-up that requires the stored
   crop and locality.
4. Confirm Cloud Run logs show successful Firestore initialization and no secret values.
5. Confirm the Firestore collection contains the private HMAC-derived session ID rather than a
   raw phone number.
6. Exercise `#reset`, outbound-error recovery, and Meta retry deduplication after deployment.

## Credential rotation

Add a new Secret Manager version for the affected Meta credential, then deploy a new Cloud Run
revision so the `latest` version is re-resolved. Verify `/health`, Meta callback verification, and
one inbound/outbound message before disabling the old Meta token. Rotation does not require
changing the permanent callback URL.

Never place secret values in this document, `.env.example`, deployment commands saved in shell
history, screenshots, logs, issues, or commits.
