# CreditFlow — Architecture

## Status
Phase 2 (auth-service) implemented and manually verified end-to-end
(signup, verify-email, login, refresh with reuse detection, logout, rate
limiting) — pytest suite in progress. Phases 3+ not started.

## Shape
- 13 FastAPI microservices under `services/`, one React (Vite) frontend
  under `frontend/`, one API Gateway in front of everything.
- Single PostgreSQL instance, one schema per service.
- RabbitMQ for async inter-service events (topic exchanges per domain:
  `billing_events`, `social_events`, `scraper_events`, `usage_events`,
  etc. — full registry in `docs/EVENT_CONTRACTS.md`).
- Single Redis instance, partitioned by logical DB index (see
  `CONVENTIONS.md`).
- MongoDB for the Scraper Service only.
- JWT auth: RS256, issued by auth-service, verified by every other service
  and the gateway using the shared public key at `keys/jwt_public.pem`.
- Local (non-Docker) dev tooling — Alembic, pytest, `uvicorn --reload` —
  connects to infra via host-published ports distinct from the ports
  containers use to reach each other internally. See `CONVENTIONS.md` for
  the exact port mapping.

## Repo strategy
Single monorepo, one folder per service under `services/`, plus `frontend/`.
Chosen because deployment (bonus) targets a single EC2 box running the whole
stack off one `docker-compose.yml` — one repo means one thing to pull/update
on that box. If AWS deployment is dropped, this structure still works fine
for local docker-compose only.

## Diagram
_(Add a request-flow / event-flow diagram once the gateway + auth + one
downstream service exist end-to-end.)_