# user-service

Owns accounts (tenants), team membership, invitations, and role
assignment. See `docs/ARCHITECTURE.md` and `docs/EVENT_CONTRACTS.md` for
the full contract with the rest of the system.

Local dev: `uvicorn app.main:app --reload --port 8002` (after `alembic
upgrade head` against a running Postgres — see repo root README for the
full docker-compose setup).