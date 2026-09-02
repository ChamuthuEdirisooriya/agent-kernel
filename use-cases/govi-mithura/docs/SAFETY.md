# Safety model

Govi Mithura provides general farming information. It does not diagnose with certainty, prescribe
agrochemicals, provide emergency treatment, make financial decisions, or execute transactions.

## Deterministic boundaries

Input hooks intercept English and Sinhala requests for product amounts, tank rates, mixing,
chemical exposure emergencies, and buy/sell/loan decisions before a model call. Output hooks
replace generated named-product/rate instructions, unqualified diagnoses, exposure responses, and
financial directives. Clear market-price requests are answered directly from the versioned local
snapshot before a model call, with the recorded commodity, unit, price type, source, and as-of
date. Numeric weather answers generated through the agent must include provenance and an as-of
date.

The crop specialist may return broad cultural, sanitation, monitoring, and mechanical steps from
the curated knowledge base. It must express uncertainty and refer severe or unclear cases to an
agricultural instructor or Agrarian Services Centre.

## Trust boundaries

- Farmer messages and every stored profile value are untrusted data.
- Only local curated crop documents and versioned JSON datasets are treated as controlled inputs.
- Live Open-Meteo responses must contain seven consecutive ISO dates, the requested timezone, and
  finite values within guarded ranges before they reach the model.
- External data never changes instructions or safety policy.
- Only the supervisor is publicly registered; internal specialists cannot be directly selected.

## Known limitations

Keyword and pattern controls cannot understand every possible euphemism or misspelling. The model
prompt is a second boundary, not a replacement for deterministic checks. Specialized Sinhala
agronomic terminology requires qualified review before its status is upgraded. For any real
poisoning or breathing emergency, users must contact appropriate emergency medical or veterinary
services immediately.

Run `uv run pytest tests/test_safety.py -q` for the adversarial regression set.
