# SPEC.md - Govi Mithura (ගොවි මිතුරා)

## Memory-aware multilingual farming support through WhatsApp

Status: Product engineering specification
Primary audience: implementation contributors
Primary SDG: SDG 2 - Zero Hunger
Secondary SDGs: SDG 8 - Decent Work and Economic Growth; SDG 13 - Climate Action

---

## 0. Specification authority

This file defines **what to build** and the acceptance criteria. It does not override the
Agent Kernel repository's current APIs or contributor rules.

Implementation contributors must:

1. Read the repository-root `CODE_OF_CONDUCT.md`, `DEVELOPER_GUIDE.md`, and every
   applicable `AGENTS.md`.
2. Inspect the current `use-cases/` examples and the installed Agent Kernel version.
3. Read the current Agent Kernel documentation for LangGraph,
   sessions/memory, tools, hooks/guardrails, CLI, and WhatsApp.
4. Use the repository's existing dependency manager, formatting, typing, testing, and
   configuration conventions.
5. Treat repository instructions and installed Agent Kernel APIs as authoritative when
   they conflict with examples or assumptions in this specification.
6. Never invent Agent Kernel imports, configuration keys, decorators, or CLI commands.
7. Keep implementation changes inside `use-cases/govi-mithura/`, unless the repository
   instructions explicitly require a minimal change elsewhere.
8. Preserve a runnable vertical slice after every architecture change.

When an API or convention is unclear, inspect the installed package and nearby official
examples before implementing it. Record any necessary deviation from this specification
in the use case README.

---

## 1. Product summary

### 1.1 Problem

Sri Lankan smallholder farmers frequently make decisions with incomplete or fragmented
information:

1. Crop symptoms may be misidentified, leading to delayed action or inappropriate and
   excessive agrochemical use.
2. Spraying, fertilizing, irrigating, and harvesting decisions may be made without
   considering short-term weather conditions.
3. Farmers may lack timely reference prices from major wholesale markets.

The information exists across agricultural publications, forecasts, and market reports,
but it is not presented as one contextual conversation that remembers the farmer's crop,
location, planting date, and preferred language.

### 1.2 Solution

Govi Mithura is a WhatsApp farming copilot that:

- remembers a farmer's town/village/locality, optional district, crops, planting dates, and
  preferred language;
- asks targeted follow-up questions instead of pretending to diagnose from vague symptoms;
- retrieves source-backed crop guidance from a curated local knowledge base;
- resolves Sri Lankan locality names and retrieves seven-day weather forecasts before providing
  general timing guidance;
- returns dated, sourced wholesale market-price information;
- applies explicit agricultural, health, financial, and scope safety rules; and
- provides the same core workflow through a CLI for local development and troubleshooting.

### 1.3 One-line pitch

> Govi Mithura remembers each farmer's field context and combines trusted crop knowledge,
> weather, and dated market information to provide safe, personalized next steps through
> WhatsApp.

### 1.4 Product boundaries

Govi Mithura is a decision-support and information system. It is **not**:

- a laboratory crop-disease diagnostic service;
- a substitute for an agricultural instructor or Agrarian Services Centre;
- an emergency medical, veterinary, or poison-control service;
- a source of pesticide prescriptions, dosage calculations, or mixing instructions;
- a trading, lending, or financial-advice service; or
- a guarantee of forecast accuracy, price availability, yield, or income.

---

## 2. Requirements and decisions

### 2.1 Agent Kernel and repository requirements

- Use a Python version supported by the checked-out Agent Kernel repository. At the time
  this specification was written, the expected range is Python 3.12-3.13; verify rather
  than hardcoding this assumption into setup scripts.
- Follow `DEVELOPER_GUIDE.md` and the current repository layout.
- Use official Agent Kernel integrations for sessions, memory, LangGraph execution,
  hooks/guardrails, CLI, and WhatsApp where those capabilities are available.
- Use the repository's current configuration names and patterns. Do not introduce a
  parallel configuration system without a demonstrated need.

### 2.2 Architecture decisions

- Agent workflow: LangGraph executed through Agent Kernel.
- Default LLM access: a generic OpenAI-compatible endpoint configured with a model ID, API key,
  and base URL. This keeps the primary setup portable across compatible providers.
- Optional Google AI Studio access: Gemini through the native Google Gen AI integration,
  authenticated with an API key. The native integration preserves Gemini thought signatures
  across multi-turn tool calls.
- Optional Cloud Run deployment access: Vertex AI through the same native integration and Google
  Application Default Credentials.
- Any provider/model must be smoke-tested for tool calling and reviewed for Sinhala quality before
  production use. Provider swaps must require configuration changes only, not farming-logic
  changes.
- Model and endpoint: configurable through environment variables; never hardcoded in
  application logic.
- Primary channel: WhatsApp through Agent Kernel's documented Meta WhatsApp Cloud API
  integration.
- Local interface: Agent Kernel CLI using the same graph and business logic.
- Tests: deterministic and offline, with live integrations validated separately.
- External data access: network-dependent in normal operation, with deterministic fixtures
  or mocks for automated testing and a graceful user-visible fallback during failures.

### 2.3 Connectivity statement

The application is not an offline system:

- Hosted Gemini API, Vertex AI, or OpenAI-compatible inference requires internet access.
- Live Open-Meteo requests require internet access.
- WhatsApp requires Meta credentials, an internet-accessible HTTPS webhook, and network
  access.
- CLI mode removes the WhatsApp-account requirement but still needs an LLM endpoint for
  live conversations.
- Automated tests must not depend on live WhatsApp, LLM, weather, or market services.

---

## 3. Product scope

### 3.1 Current release

The current release includes:

- Channels: CLI and WhatsApp text messaging.
- Languages: English and Sinhala for the supported and tested flows.
- Crops: chili and paddy.
- Crop knowledge: at least three well-sourced symptom/problem topics for each supported crop.
- Weather: Sri Lankan towns, villages, and localities resolved through Open-Meteo geocoding, plus
  all 25 districts using documented representative coordinates.
- Markets: dated reference prices for Dambulla, Colombo/Pettah, and Meegoda when data is
  available.
- Memory: locality or district, crops, planting dates, preferred language, and recent topic
  context.
- Routing: crop guidance, weather guidance, market information, profile update, and
  small-talk/out-of-scope behavior.
- Safety: all guardrails in section 8.
- Reliability: structured tool outputs, timeouts, graceful failures, and deterministic
  automated tests.

### 3.2 Planned features

Add these only after the current acceptance criteria pass:

- Tamil responses.
- Tomato, brinjal/eggplant, and okra knowledge.
- Crop images or voice notes.
- Live or automated HARTI report ingestion.
- Additional production session backends such as Redis. The maintained GCP deployment uses
  Firestore rather than Redis.
- Additional messaging channels.

### 3.3 Explicitly out of scope

- Definitive image-based crop diagnosis.
- Chemical product selection, dosage, concentration, or mixing guidance.
- Automated buying or selling recommendations.
- Payments, lending, insurance decisions, or marketplace transactions.
- Autonomous contact with agricultural officers or third parties.
- Group-chat coordination.

---

## 4. User roles and core journeys

### 4.1 Farmer

The only current user role is a farmer interacting through WhatsApp or CLI.

### 4.2 Journey A - opportunistic onboarding

The first interaction should not become a questionnaire. Collect profile fields naturally.

Example:

```text
Farmer: I planted chili last week in Wellawaya.
Agent: Got it - chili planted around 4 July in Wellawaya. Would you like advice about
       the crop, weather, or market prices?
```

Requirements:

- Store only information the farmer provides or explicitly confirms.
- Allow partial profiles.
- Preserve farmer-provided localities without inventing a district, and confirm crop or location
  names when interpretation is uncertain.
- Do not repeatedly ask for optional fields that are irrelevant to the current request.

### 4.3 Journey B - symptom triage

```text
Farmer: My chili leaves are curling.
Agent: Are they curling upward or downward? Can you see small white insects beneath the
       leaves, and is this across the field or only in patches?
```

Requirements:

- Ask a focused clarifying question when the evidence is insufficient.
- Retrieve relevant knowledge before answering a supported crop question.
- Present possibilities and uncertainty, not a definitive diagnosis.
- Prefer cultural/mechanical measures and monitoring steps.
- Cite the knowledge source in a concise user-friendly form.
- Refer uncertain or severe cases to an agricultural instructor or Agrarian Services
  Centre.

### 4.4 Journey C - weather-aware guidance

```text
Farmer: What is tomorrow's weather in Wellawaya?
Agent: Wellawaya was resolved within Monaragala District. Rain is forecast tomorrow afternoon,
       with stronger wind around ...
       Consider completing rain-sensitive work earlier if conditions remain suitable.
       Follow any product label and local agricultural guidance. Source: Open-Meteo,
       updated ...
```

Requirements:

- Use the most specific confirmed stored locality or district unless the farmer specifies a
  different location.
- Disclose whether coordinates came from locality geocoding or a district representative point.
- State forecast source and update/as-of time.
- Distinguish weather facts from general guidance.
- Never prescribe a chemical, dose, mixture, or application interval.
- Avoid absolute claims such as "safe to spray" or "guaranteed dry."

### 4.5 Journey D - market-price information

```text
Farmer: What is the chili price in Dambulla?
Agent: The available Dambulla wholesale reference for green chili is Rs ... per kg,
       dated ... Source: HARTI ... This is reference information, not a guaranteed buyer
       price.
```

Requirements:

- Always show commodity, market, unit, wholesale/retail classification, data date, and
  source.
- Never describe seeded or old data as live/current without qualification.
- If data exceeds the configured staleness threshold, show a prominent stale-data warning.
- Never tell the farmer to buy, sell, hold, borrow, or choose a specific buyer.

### 4.6 Journey E - returning farmer

The returning interaction is the primary proof of Agent Kernel memory.

```text
Agent: Welcome back. How is your chili crop in Monaragala doing?
```

Requirements:

- The same WhatsApp phone number/session must retrieve its existing profile while the
  configured backing store remains available.
- Do not imply that in-memory storage survives an agent-server restart.
- A configured persistent backend such as Firestore or Redis should preserve the profile across
  process restarts while the record remains available.
- `#reset` must require confirmation and then clear the farmer profile and conversation
  state for that user only.

---

## 5. Agent and graph architecture

Use a small, inspectable LangGraph. Do not create agents solely to inflate an agent count.

### 5.1 Runtime and graph state

The implemented LangGraph uses `MessagesState`, so LangGraph and Agent Kernel manage conversation
messages without a duplicate application-specific history schema. Other state is deliberately kept
at the boundary where it belongs:

- Agent Kernel owns the session identifier and session lifecycle.
- The validated farmer profile and bounded recent-topic list live in the session's non-volatile
  cache.
- Pre-hooks classify the current request, decide deterministic reply language, and inject a compact
  trusted-context envelope containing the intent hint, language guidance, and an explicitly
  untrusted profile snapshot.
- LangGraph tool messages carry crop evidence, weather results, market results, and profile-tool
  results during the active turn.
- Agent Kernel pre/post hooks enforce deterministic commands and safety outcomes outside the graph.

Do not add parallel message history or copy session/profile state into a custom graph state unless a
verified future requirement cannot be met by these existing mechanisms.

### 5.2 Nodes/responsibilities

#### Context and profile loader

- Load session and non-volatile profile data.
- Handle the confirmed `#reset` path deterministically.
- Normalize known crop, district, language, and planting-date fields while preserving a supplied
  town, village, or locality.

#### Router/supervisor

- Classify one primary intent:
  - `crop_problem`
  - `weather_advice`
  - `market_price`
  - `profile_update`
  - `smalltalk_or_other`
- Detect profile information embedded in ordinary messages.
- Route to exactly one primary branch per turn.
- Use deterministic handling for commands and obvious structured cases where practical.

#### Crop knowledge specialist

- Search the curated crop knowledge base.
- Decide whether a clarifying question is needed.
- Generate a source-grounded, uncertainty-aware response.
- Never answer unsupported-crop questions as though the local KB covered them.

#### Field information specialist

- Call weather or market tools based on the routed intent.
- Interpret structured results using farmer context.
- Preserve source, timestamp, unit, and staleness information.

#### Profile updater

- Validate and persist confirmed profile changes.
- Do not overwrite existing values silently when the new interpretation is ambiguous.

#### Safety and response validator

- Apply deterministic rules and Agent Kernel-supported hooks/guardrails.
- Validate both unsafe requests and unsafe generated output.
- Replace or revise responses that violate section 8.
- Ensure required sources/timestamps are present for data-backed claims.

### 5.3 Routing principles

- Prefer deterministic routing for `#reset`, clear crop-problem requests, clear weather requests,
  and clear market-price requests. Keep the LLM supervisor as the fallback for profile updates,
  greetings, and requests without a recognized deterministic route.
- The current classifier selects one primary intent using the priority market, weather, profile,
  crop, then other. It does not fan one turn out to multiple specialists; documentation and user
  guidance must not claim complete multi-intent handling.
- Use the LLM for ambiguous natural-language classification and response generation.
- Do not make an LLM call when a deterministic command handler is sufficient.
- Tool failure must never be interpreted as an empty but valid result.
- The graph must terminate safely after bounded retries; no unbounded agent loops.

---

## 6. Memory and profile design

### 6.1 Farmer profile

Use a typed schema equivalent to:

```text
FarmerProfile
  schema_version: integer
  name: optional string
  location: optional farmer-provided town, village, or locality
  district: optional canonical district identifier
  crops: list of canonical crop identifiers
  planting_dates: map[crop identifier, ISO date]
  preferred_language: optional enum[en, si]
  last_topics: bounded list of short topic identifiers
  created_at: timestamp
  updated_at: timestamp
```

Do not store health details, national identity numbers, exact home addresses, financial
records, or other unnecessary sensitive data.

Tamil remains a stretch feature and must not be added to the stored language enum until its
language and safety acceptance gates pass.

### 6.2 Storage semantics

- Short-term conversation state belongs in the Agent Kernel/LangGraph session mechanism.
- Farmer preferences and profile metadata belong in the appropriate Agent Kernel
  non-volatile/session memory mechanism supported by the installed version.
- Default development mode may use in-memory storage.
- The optional Cloud Run deployment uses Firestore with a seven-day TTL; optional Redis
  configuration may be included for other environments if supported by repository conventions.
- Documentation must accurately state the durability of each backend.
- Profile reads and writes must be isolated by user/session identifier.

### 6.3 Date handling

- Store dates in ISO `YYYY-MM-DD` form.
- Resolve relative phrases such as "last week" using the current date and timezone only
  when sufficiently unambiguous; otherwise ask for confirmation.
- Use `Asia/Colombo` for farmer-facing dates and times unless the runtime provides an
  explicit user timezone.

---

## 7. Tools and data contracts

Application tools return validated structured results serialized as JSON text at the model
boundary, not free-form prose. Weather and market results include `source`, `as_of`, and a
machine-readable status, including on error paths.

### 7.1 Crop knowledge search

Implemented interface:

```text
crop_kb_search(crop, query, top_k=3) -> JSON text containing
  status
  crop
  matches[]:
    document_id
    title
    excerpt
    score
    source_title
    source_publisher
    source_url
    source_date
```

Requirements:

- Keep source documents under `data/crop_kb/` or the repository-approved equivalent.
- Record title, publisher, publication date when known, URL/reference, retrieval date, and
  covered crop/topic.
- Prefer official Sri Lankan Department of Agriculture material and other authoritative
  agricultural sources.
- Use a simple deterministic retrieval baseline if it is adequate. Do not introduce a
  vector database merely for novelty.
- If embeddings are used, configure the embedding model externally and cache/index data so
  the KB is not re-embedded on every request.
- Return `unsupported_crop` or `no_relevant_match` explicitly when appropriate.

### 7.2 Weather forecast

Implemented interface:

```text
get_weather_forecast(location) -> successful JSON result containing
  status
  requested_location
  resolved_location
  district: optional canonical or geocoded administrative district
  representative_location
  coordinates:
    latitude
    longitude
  location_resolution: human-readable description of named-locality or district coordinates
  location_source
  location_source_url: present for geocoded localities
  timezone
  forecast[]:
    date
    temperature_max_c
    temperature_min_c
    precipitation_mm
    precipitation_probability_percent
    wind_speed_max_kmh
  source
  source_url
  as_of
  limitation
```

Error results contain `status`, a safe `message`, `source`, `source_url`, and `as_of`.

Requirements:

- Use Open-Meteo with explicit timeouts.
- Resolve non-district locality names through Open-Meteo Geocoding with results restricted to Sri
  Lanka, validate returned coordinates, and use the resolved point for the forecast.
- Maintain all 25 canonical districts and representative coordinates in a versioned local data
  file with an explicit review status. The current seed coordinates remain pending independent
  geographic review and must not be described as independently verified.
- Disclose whether a forecast uses geocoded locality coordinates or a representative district
  coordinate and that neither path reflects field-level microclimates.
- Return a structured error on invalid locations, geocoding failures, timeouts, rate limits,
  malformed responses, or upstream failures.

### 7.3 Market prices

Implemented interface:

```text
get_market_prices(commodity, market="") -> successful JSON result containing
  status
  commodity
  records[]:
    market
    price_min_lkr
    price_max_lkr
    unit
    price_type
    data_date
  source
  source_url
  as_of
  stale
  data_age_days
  stale_after_days
  limitation
```

Unavailable commodity/market results contain `status=not_found`, a safe `message`, available
options where applicable, `source`, `source_url`, and `as_of`; they never substitute another record.

Requirements:

- Use a versioned local dataset derived from documented HARTI reports for the current release.
- Include provenance for every imported record.
- Do not fabricate missing values or silently substitute a different commodity/market.
- Make the staleness threshold configurable, with a documented default.
- A future refresh script may download/parse new reports, but it must not be presented as
  implemented unless it is tested and operational.

### 7.4 Crop-age calculation

Use deterministic date arithmetic rather than an LLM. The implemented tool returns JSON text:

```text
calculate_crop_age(planting_date, as_of_date="") ->
  planting_date
  as_of_date
  age_days
  age_weeks
```

### 7.5 MCP boundary

MCP is optional unless the current Agent Kernel examples make it straightforward
and reliable. Correct Agent Kernel usage is more important than adding MCP for its own sake.

If MCP is used:

- expose weather and market access through a small local MCP server;
- keep crop retrieval in-process unless there is a clear interoperability benefit;
- include health checks, startup instructions, timeouts, and failure tests; and
- ensure CLI/WhatsApp startup does not silently succeed when required MCP tools are absent.

If MCP threatens product stability, implement typed Agent Kernel-compatible Python tools first
and document MCP as a stretch goal.

---

## 8. Safety and response policy

Safety is load-bearing and must be enforced through more than prompt wording. Combine
deterministic checks with Agent Kernel-supported pre/post hooks or guardrails.

### 8.1 Agrochemical safety

The system must not provide:

- specific pesticide, fungicide, herbicide, or chemical product recommendations;
- dosages, concentrations, dilution ratios, or mixing instructions;
- tank-mix combinations;
- application intervals or pre-harvest intervals presented as prescriptions; or
- claims that a chemical application is definitively safe.

It may provide:

- cultural and mechanical controls;
- monitoring and sanitation steps;
- broad problem categories with uncertainty;
- general weather considerations; and
- referral to a product label, agricultural instructor, or Agrarian Services Centre.

### 8.2 Human and animal health

Questions involving poisoning, exposure, ingestion, breathing difficulty, burns, or human/
animal illness must receive an immediate referral to appropriate emergency, medical, or
veterinary help. The farming agent must not attempt treatment advice.

Do not hardcode emergency numbers unless they have been verified from an authoritative,
current Sri Lankan source.

### 8.3 Financial safety

- Market prices are informational reference data.
- Do not instruct the farmer to buy, sell, hold, borrow, take a loan, or choose a buyer.
- Do not predict guaranteed price movements, profit, or yield.

### 8.4 Scope fence

Off-topic requests receive a brief redirect to supported farming topics. Do not engage in
extended unrelated assistance.

### 8.5 Uncertainty and provenance

- Never claim a definitive diagnosis from text symptoms alone.
- State when evidence is incomplete or the crop is unsupported.
- Weather and price claims require source and timestamp/date.
- Retrieved crop guidance requires a human-readable source reference.
- If required source data is unavailable, provide only clearly labeled general guidance.

### 8.6 Multilingual enforcement

Safety checks must cover Sinhala and English inputs and outputs. Do not assume English-only
keyword filters are sufficient. Tamil safety behavior is required before Tamil is promoted
from stretch status.

---

## 9. Language behavior

- Detect the language of each message while respecting a stored preference.
- Respond in the user's current language unless they request another language.
- Preserve crop names, measurements, dates, prices, and source names accurately during
  translation.
- Keep responses concise enough for messaging.
- Avoid technical agricultural terminology when a plain-language equivalent is available.
- When a Sinhala translation is uncertain, preserve the recognized English term in
  parentheses rather than inventing terminology.
- Maintain a small reviewed terminology glossary for supported crops, symptoms, markets, units,
  safety referrals, and districts.

---

## 10. Configuration and secrets

Commit `.env.example`; never commit live credentials.

The exact environment-variable names follow the installed Agent Kernel and provider clients. The
implemented configuration is:

```text
# Provider and model
LLM_PROVIDER                 # openai_compatible (default), google_ai_studio, or google_vertex
LLM_MODEL
LLM_THINKING_LEVEL           # optional native Gemini latency/quality control
LLM_REQUEST_TIMEOUT_SECONDS  # timeout for each model attempt; default 30
LLM_MAX_RETRIES              # retries after the initial attempt; default 1
GEMINI_API_KEY               # required for the AI Studio path
GOOGLE_CLOUD_PROJECT         # required for Vertex ADC
GOOGLE_CLOUD_LOCATION        # global by default
LLM_BASE_URL                 # generic OpenAI-compatible providers
LLM_API_KEY                  # required for OpenAI-compatible providers

# Agent Kernel session backend; config.yaml uses in_memory when these are absent
AK_SESSION__TYPE                         # in_memory locally; firestore in the Cloud Run example
AK_SESSION__FIRESTORE__COLLECTION_NAME   # only when Firestore is enabled
AK_SESSION__FIRESTORE__PROJECT_ID        # only when Firestore is enabled
AK_SESSION__FIRESTORE__DATABASE_ID       # only when Firestore is enabled
AK_SESSION__FIRESTORE__TTL               # seconds; Cloud Run example uses 604800

# WhatsApp Cloud API; required only for server.py
AK_WHATSAPP__VERIFY_TOKEN
AK_WHATSAPP__ACCESS_TOKEN
AK_WHATSAPP__APP_SECRET
AK_WHATSAPP__PHONE_NUMBER_ID
AK_WHATSAPP__API_VERSION                 # default v25.0

# Application behavior
MARKET_PRICE_STALE_AFTER_DAYS
WEATHER_REQUEST_TIMEOUT_SECONDS
```

`GEMINI_API_KEY` also accepts the documented `GOOGLE_API_KEY` or `LLM_API_KEY` aliases. Generic
OpenAI-compatible configuration also accepts `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Embeddings,
Redis, and an environment-based `LOG_LEVEL` are not implemented; Agent Kernel logging levels are
configured in `config.yaml`.

Requirements:

- Changing the LLM model or compatible endpoint must not require code changes.
- Validate required configuration at startup and emit actionable errors without printing
  secret values.
- Redact tokens and personal profile values from normal logs.
- Pin or lock dependencies according to repository conventions.

---

## 11. Repository layout

The implemented repository layout is:

```text
use-cases/govi-mithura/
|-- README.md
|-- docs/
|   |-- SPEC.md
|   |-- SAFETY.md
|   |-- WHATSAPP_SETUP.md
|   `-- CLOUD_RUN.md
|-- .env.example
|-- pyproject.toml
|-- uv.lock
|-- build.sh
|-- config.yaml
|-- agent.py                   # model factory, graph, internal specialists, registration
|-- demo.py                    # Agent Kernel CLI entry point
|-- server.py                  # Agent Kernel WhatsApp/API entry point and log redaction
|-- whatsapp_runtime.py        # webhook validation, private session IDs, retry deduplication
|-- settings.py                # provider-explicit environment settings
|-- farmer_profile.py
|-- tools.py
|-- field_tools.py
|-- knowledge.py
|-- routing.py
|-- hooks.py
|-- safety.py
|-- language.py
|-- trusted_context.py
|-- session_compat.py
|-- Dockerfile
|-- data/
|   |-- crop_kb/
|   |-- districts.json
|   |-- market_prices.json
|   `-- sinhala_glossary.json
`-- tests/                     # offline unit, integration, security, and regression tests
```

There is no MCP server, embeddings layer, automated data-refresh script, Redis adapter, or bundled
asset directory in the current release.

All crop and price data files must include provenance either inside the file or in a nearby
manifest.

---

## 12. Testing requirements

Tests must be deterministic, must not require paid credentials, and must not call live
external services. Follow the Agent Kernel repository's supported test framework and
pytest conventions where applicable.

### 12.1 Unit tests

- District and crop normalization.
- Relative/absolute planting-date parsing and confirmation behavior.
- Crop-age calculation.
- Price staleness calculation.
- Structured schema validation for all tool results.
- Deterministic guardrail rules.
- Profile merge/update behavior.
- `#reset` confirmation and user isolation.

### 12.2 Routing tests

At minimum:

- English crop symptom request -> crop branch.
- Sinhala crop symptom request -> crop branch.
- Weather question -> field/weather branch.
- Market-price question -> field/market branch.
- Natural-language profile update -> profile update behavior.
- Small talk -> brief supported response.
- Off-topic request -> scope redirect.
- Confirmed `#reset` -> deterministic reset path.

### 12.3 Memory tests

- Store a locality, crop, and planting date in one interaction.
- Retrieve them in a later interaction for the same session/user.
- Do not expose them to a different session/user.
- Returning-farmer response uses stored crop and locality appropriately.
- In-memory behavior is not falsely tested or documented as surviving process restart.
- Persistent-backend tests may be optional/integration-marked when they require cloud or Redis
  infrastructure; deployment acceptance must still exercise the configured live backend.

### 12.4 Retrieval tests

- Known chili leaf-curl query retrieves the intended authoritative document/topic.
- A known paddy problem retrieves the intended document/topic.
- Unsupported crop returns an explicit unsupported result.
- Irrelevant query does not produce fabricated crop evidence.

### 12.5 Tool tests

- Valid locality geocodes within Sri Lanka and returns a structured forecast fixture.
- Valid district bypasses geocoding and returns its representative-point forecast.
- Unknown or non-Sri Lankan locations return a structured error.
- Weather timeout/upstream error produces graceful fallback behavior.
- Known commodity/market returns dated and sourced fixture data.
- Unknown commodity/market returns `not_found` without substitution.
- Stale price data is visibly labeled stale.

### 12.6 Safety tests

At minimum, test English and Sinhala variants for:

- request for a pesticide dosage;
- request for a product recommendation or mixing ratio;
- poisoning or chemical exposure;
- request to decide whether to sell or borrow money;
- unsupported definitive diagnosis request;
- generated answer missing a required price/weather source;
- prompt injection attempting to disable safety rules.

Tests must assert prohibited information is absent, not merely that a disclaimer is present.

### 12.7 End-to-end tests

Using mocked LLM/tool responses where necessary:

1. onboard farmer -> store profile -> return later -> personalized context;
2. symptom report -> clarification -> grounded safe guidance;
3. weather request -> tool result -> timestamped qualified guidance;
4. market request -> dated result -> stale warning when applicable;
5. tool outage -> no fabricated forecast or price;
6. unsafe chemical request -> blocked/referred response.

---

## 13. Observability and failure behavior

Implemented behavior:

- Agent Kernel supplies the repository-consistent runtime logs.
- WhatsApp session identifiers are stable HMAC digests rather than phone numbers.
- Startup log filters redact verification/access tokens, long identifiers, complete webhook bodies,
  and status payloads from the framework loggers that receive them.
- Application error logs name the failure class without rendering secret values or farmer content.
- Open-Meteo calls use an explicit timeout and transparent structured errors. They are not retried
  automatically; Meta delivery retries are handled through bounded duplicate-message suppression.
- Failed weather/price lookups produce transparent unavailable or `not_found` responses.
- User-facing processing failures return a concise generic apology.

Custom per-turn route/tool-status/latency/guardrail metrics are not implemented. If added later,
their correlation identifier must not expose a phone number, and a failed memory write or safety
validator must fail closed rather than being acknowledged as successful.

---

## 14. README and documentation requirements

The README must contain the following material in a clear order:

1. Title and one-line pitch.
2. Sri Lankan problem statement and SDG 2 mapping.
3. Solution overview and current product scope.
4. Architecture diagram showing:
   - WhatsApp and CLI;
   - Agent Kernel runtime/session handling;
   - LangGraph router and specialists;
   - memory/profile storage;
   - crop retrieval;
   - weather and market tools;
   - safety validation.
5. Why Agent Kernel is essential to the solution.
6. Prerequisites.
7. CLI-first quickstart using the repository's verified commands.
8. Configuration reference.
9. WhatsApp Cloud API setup using Agent Kernel's official integration, with optional local tunnel
   and permanent Cloud Run paths clearly separated.
10. Commands for CLI, WhatsApp/API mode, tests, formatting, and type checks.
11. Example English and Sinhala conversation behavior.
12. Data sources, dates, provenance, and staleness behavior.
13. Safety and network limitations.
14. Troubleshooting.
15. Roadmap/stretch features.

Additional documentation:

- `docs/SAFETY.md`: threat model, prohibited outputs, escalation language, and safety tests.
- `docs/WHATSAPP_SETUP.md`: local Meta and temporary-tunnel setup.
- `docs/CLOUD_RUN.md`: optional permanent deployment and credential-rotation procedure.

Do not claim a feature is implemented unless it passes its acceptance test.

---

## 15. Operational acceptance criteria

- CLI and WhatsApp use the same Agent Kernel/LangGraph workflow.
- English and Sinhala user journeys preserve farmer context and session isolation.
- Chili and paddy retrieval remains source-backed and uncertainty-aware.
- Weather and price outputs contain source and date/time information.
- Stale and unavailable data are clearly labeled.
- Prohibited agricultural, health, and financial outputs are blocked in English and Sinhala.
- Automated tests pass without live external services.
- Live provider, weather, and WhatsApp checks are completed before a production release.
- No secrets or unnecessary personal data appear in the repository or logs.
