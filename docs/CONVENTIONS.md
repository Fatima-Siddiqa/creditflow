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

## Service independence (testing)
Every service's pytest suite runs against **real Postgres and Redis**
(each test wrapped in a transaction that's rolled back afterward, so
nothing persists), with **RabbitMQ mocked** (an in-memory list standing in
for `publish_event`, via `monkeypatch`). This is not a pure
everything-mocked unit-test setup — that would require a repository/
interface layer between endpoints and the DB, which this project doesn't
use, and retrofitting one costs more than any single phase can absorb.
What actually matters: no other *service* (of the 13) needs to be running
for a given service's tests to pass — only the shared Postgres/Redis
containers from `docker-compose.yml`.

## Local (non-Docker) dev tooling needs published host ports
Every infra service in `docker-compose.yml` is reachable from **other
containers** via its internal hostname/port — but Alembic, pytest, and
`uvicorn --reload` run directly on the host, not in a container, so they
need a **host-published port** instead. `docker-compose.override.yml` maps
each infra service to a distinct host port, chosen to avoid colliding with
anything that might already be running locally on the standard port:

| Service | Internal (container-to-container) | Host-published (local tooling) |
|---|---|---|
| postgres | `postgres:5432` | `localhost:5433` |
| redis | `redis:6379` | `localhost:6380` |
| rabbitmq | `rabbitmq:5672` | `localhost:5673` |

Every service's `app/config.py` default should use the host-published
values (what you run locally most of the time); the *container* version of
each URL only applies inside that service's own `docker-compose.yml`
entry, via its `environment:` block.

## Dockerfile pattern
No `--reload` in the container `CMD` — that's a local-dev convenience
only. Every service listens on port 8000 *inside* its own container
regardless of what host port it's mapped to locally; `docker-compose.yml`
(or the gateway, once built) decides host-facing ports, not the service
itself.

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
| 15 | all services (test suites) | shared, flushed per-test — safe to share since only one service's tests run at a time in this solo workflow |

## PostgreSQL
Single instance, **one schema per service** — not one database per service.
Each service's Alembic config targets only its own schema. No service reads
another service's tables directly — cross-service data comes from REST
calls or consumed events, never a shared-schema join.