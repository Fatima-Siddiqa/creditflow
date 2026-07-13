# CreditFlow — Architecture

## Status
Phase 0: skeleton only, no services implemented yet. This doc grows as each
phase lands.

## Shape
- 13 FastAPI microservices under `services/`, one React (Vite) frontend
  under `frontend/`, one API Gateway in front of everything.
- Single PostgreSQL instance, one schema per service.
- RabbitMQ for async inter-service events (topic exchanges per domain:
  `billing_events`, `social_events`, `scraper_events`, `usage_events`).
- Single Redis instance, partitioned by logical DB index (see
  `CONVENTIONS.md`).
- MongoDB for the Scraper Service only.
- JWT auth: RS256, issued by auth-service, verified by every other service
  and the gateway using the shared public key at `keys/jwt_public.pem`.

## Repo strategy
Single monorepo, one folder per service under `services/`, plus `frontend/`.
Chosen because deployment (bonus) targets a single EC2 box running the whole
stack off one `docker-compose.yml` — one repo means one thing to pull/update
on that box. If AWS deployment is dropped, this structure still works fine
for local docker-compose only.

## Diagram
_(Add a request-flow / event-flow diagram once the gateway + auth + one
downstream service exist end-to-end.)_