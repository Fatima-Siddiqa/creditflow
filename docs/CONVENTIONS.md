# CreditFlow — Cross-Service Conventions

Every service in `services/` must follow these, so a service built in
isolation still behaves consistently with the other 12.

## Error response schema
Every service returns errors in this shape, regardless of framework defaults:

\`\`\`json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
\`\`\`

`code` is a stable machine-readable string (e.g. `"invalid_credentials"`,
`"insufficient_credits"`), not an HTTP status text. `message` is human
readable. `details` is optional, free-form context. The API Gateway passes
a downstream service's error body through as-is when proxying — it only
adds its own error shape for gateway-level failures (auth rejected, rate
limited, upstream down).

## Health checks
Every service exposes:
- `GET /healthz` → `{"status": "ok"}` — liveness only, no dependency checks.
  Used by Docker healthchecks.
- `GET /readyz` → actually pings its DB connection (and broker connection,
  if it's a consumer) and returns 200/503 accordingly.

## Naming
- snake_case for DB columns and JSON keys (`account_id`, `created_at`).
- kebab-case for URL paths (`/api/social-connections`).
- Event names are `noun.past_tense_verb` (`invoice.paid`, `content.scheduled`)
  — full registry lives in `docs/EVENT_CONTRACTS.md`.

## Service independence
- Every service's `main.py` runs standalone: `uvicorn app.main:app`.
- Every service's pytest suite passes with **no other service running**.
  Mock RabbitMQ publishes/consumes and DB calls in unit tests. Tests that
  need real Postgres/RabbitMQ/Redis are integration tests, run separately
  against docker-compose — not part of the fast unit suite CI runs on
  every push.

## Git / commits
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- One functional requirement per commit/PR where practical.
- `main` (protected) ← `dev` (protected) ← `feature/*` / `fix/*`.

## Redis logical DB index scheme
Single Redis instance, separated by logical DB index:

| Index | Owner | Purpose |
|---|---|---|
| 0 | api-gateway | rate-limit counters, webhook dedup keys, SSE channel subscriptions |
| 1 | auth-service | active jti store |
| 2 | scheduler-service | Celery broker + result backend |
| 3 | ai-generation-service / api-gateway | SSE token pub/sub fan-out |
| 4 | usage-service | live per-account usage counters |

## PostgreSQL
Single instance, **one schema per service** — not one database per service.
Each service's Alembic config targets only its own schema. No service reads
another service's tables directly — cross-service data comes from REST
calls or consumed events, never a shared-schema join.