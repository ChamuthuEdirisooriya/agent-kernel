# WhatsApp Cloud API setup

Govi Mithura uses Agent Kernel's official `AgentWhatsAppRequestHandler`. CLI and WhatsApp
register the same `govi_mithura` LangGraph workflow; there is no channel-specific agent logic.

## Required configuration

Create a Meta Business app with the WhatsApp product and obtain a test or production phone-number
ID, access token, and app secret. Create a separate random verify token. Export:

```bash
export AK_WHATSAPP__VERIFY_TOKEN="..."
export AK_WHATSAPP__ACCESS_TOKEN="..."
export AK_WHATSAPP__APP_SECRET="..."
export AK_WHATSAPP__PHONE_NUMBER_ID="..."
export AK_WHATSAPP__API_VERSION="v25.0"
```

The app secret is mandatory for Govi Mithura even though upstream Agent Kernel permits omitting
it. Startup fails closed when any credential is absent. Never commit these values or paste them
into screenshots, logs, issues, or other shared artifacts.

Configure exactly one LLM provider using `.env.example`. The primary path uses an
OpenAI-compatible model, API key, and endpoint. Google AI Studio and Vertex AI are alternatives,
not additional requirements.

## Run and register the webhook

```bash
uv run python server.py
```

Expose port 8000 through an HTTPS tunnel or deployment. In Meta's WhatsApp configuration:

- callback URL: `https://YOUR_HOST/whatsapp/webhook`
- verify token: the exact `AK_WHATSAPP__VERIFY_TOKEN` value
- subscribed webhook field: `messages`

Use `GET /health` to check that the server is running. A successful health response does not test
Meta delivery, LLM credentials, or outbound WhatsApp authorization.

### Optional local Cloudflare quick tunnel

With `cloudflared` installed and `server.py` still running in one terminal, start a second terminal
and run:

```bash
cloudflared tunnel --url http://localhost:8000
```

Use the generated `https://...trycloudflare.com/whatsapp/webhook` URL as the Meta callback. A quick
tunnel is temporary: the local server and `cloudflared` process must remain running, and a new
hostname is assigned after reconnection. Update and reverify the Meta callback whenever that
hostname changes.

Cloud Run is not required for local testing. If a permanent callback and restart-persistent
sessions are useful, use the optional deployment documented in
[CLOUD_RUN.md](CLOUD_RUN.md).

## Security and session behavior

- Incoming POST bodies require a valid `X-Hub-Signature-256` HMAC created with the app secret.
- The verify token protects Meta's initial GET challenge.
- The server installs log filters before startup so verification-token query values, long Meta
  identifiers, complete webhook bodies, and status payloads are not rendered by the framework's
  normal or debug loggers. Keep this filter enabled when changing server startup or log levels.
- Govi Mithura derives a stable HMAC session ID from the sender number. Messages from one number
  reuse that farmer's configured session; a different number receives an isolated session, while
  the full phone number is not passed to Agent Kernel's session store or normal logs.
- Concurrent signed deliveries with the same WhatsApp message ID are ignored while one copy is in
  flight. An ID enters the bounded 24-hour completed cache only after an outbound response or safe
  fallback is delivered; failed delivery releases the claim so a later retry can run.
- Local session storage is in-memory. Restarting the local process loses remembered profiles.
- The optional Cloud Run deployment uses Firestore with seven-day expiry, so sessions can
  survive scale-to-zero and service revisions. Expired or explicitly reset sessions are removed.
- Production deployment must terminate HTTPS securely and keep secrets in a secret manager; the
  documented Cloud Run path uses Google Secret Manager.

## Offline verification

`uv run pytest tests/test_whatsapp.py -q` checks configuration failures, verification-token
handling, invalid and valid HMAC signatures, text dispatch, retry deduplication, and private
phone-number session isolation.
No Meta request or real message is sent by this suite.
