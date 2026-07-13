# CreditFlow

Multi-tenant, credit-based SaaS platform for AI-assisted content generation
and social publishing. Internship capstone project, Adept Tech Solutions.

**Status:** Phase 0 — repo skeleton + infra only. No application services
implemented yet.

## Stack
FastAPI (all services) · React (Vite) + Tailwind · PostgreSQL · Redis ·
RabbitMQ · MongoDB (scraper only) · Stripe (sandbox) · OpenRouter ·
LinkedIn API · Docker Compose.

## Repo layout
Single monorepo — see `docs/ARCHITECTURE.md` for the full rationale.
\`\`\`
creditflow/
  docker-compose.yml        # infra (Phase 0), app services added per-phase
  docs/                      # architecture, event contracts, conventions, DoD
  keys/                      # RS256 JWT keypair (private key gitignored)
  services/<name>/           # one FastAPI service per folder, 13 total
  frontend/                  # single React app, role-gated routing
\`\`\`

## Running locally
\`\`\`bash
cp .env.example .env   # fill in real values as each phase requires them
docker compose up -d postgres redis rabbitmq mongodb
docker compose ps      # all four should report healthy
\`\`\`
RabbitMQ management UI: http://localhost:15672 (guest/guest)

## Docs
- `docs/ARCHITECTURE.md` — system shape, decisions
- `docs/CONVENTIONS.md` — error schema, health checks, naming, Redis index map
- `docs/EVENT_CONTRACTS.md` — event envelope + exchange topology
- `docs/DEFINITION_OF_DONE.md` — acceptance checklist