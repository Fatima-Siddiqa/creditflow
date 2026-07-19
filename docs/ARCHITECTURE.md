# CreditFlow — Architecture

## Status
Phase 2 (auth-service) and Phase 3 (api-gateway) implemented and
pytest-covered end-to-end. Phase 4 (user-service): PRs #1-5 and the
billing-events consumer merged. PR #6 (member role update + removal,
with the last-owner guard) closes the final literal spec §8 Service 3
gap — Phase 4 is now feature-complete pending this PR's merge. Phase 5
(billing-service) not started.

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

## Internal cross-service calls
### Account-scoped JWT issuance (auth-service ← user-service, Phase 4)
Per spec §4 (Account Switcher: "triggers a new account-scoped JWT"), a user
switching accounts (or accepting a team invite) needs a fresh JWT carrying
the new `account_id`/`role`. Login itself issues an account-agnostic token
(`account_id`/`role` both null) since Auth Service owns identity, not
membership — only User/Tenant Service (Phase 4) knows which accounts a user
belongs to and with what role.

`auth-service` exposes `POST /auth/issue-scoped-token` for this:
- **Caller:** User/Tenant Service only, server-to-server — never the
  browser, never routed through the frontend.
- **Auth:** shared secret via `X-Internal-Secret` header, checked against
  `INTERNAL_SERVICE_SECRET` (both services must be configured with the same
  value). Not JWT-based, since the caller isn't a logged-in user here.
- **Trust boundary:** auth-service does **not** re-verify account
  membership — it trusts that the caller (user-service) already confirmed
  `user_id` belongs to `account_id` with `role`. auth-service only checks
  that `user_id` exists and is verified.
- **Request:** `{"user_id": uuid, "account_id": uuid, "role": string}`
- **Response:** `{"access_token": string, "token_type": "bearer"}` — no
  refresh token. The user's original (account-agnostic) refresh token from
  login keeps working regardless of which account is currently active;
  only the access token is re-scoped.
- **Session semantics:** issuing a scoped token does not revoke the caller's
  other jtis — a user may hold concurrently valid sessions across multiple
  accounts (e.g. two browser tabs on two workspaces).
- **Gateway exposure:** since `/api/auth/*` is proxied generically (Phase
  3's route map has no per-route allow/deny), this endpoint IS reachable
  from outside if someone knows the path — it's the shared secret, not
  network position, that actually protects it. Revisit if the gateway ever
  grows route-level access control.

Login issues an identity-only token — scoping is a required follow-up

Per spec §8 Service 2, the JWT a login call returns must carry
account_id/role. Taken completely literally, that would mean Auth
Service needs to know a user's account at the moment of login — but Auth
Service owns identity only (no account tables, per CONVENTIONS.md's "no
service reads another's schema"), and User/Tenant Service is a separate
deployable unit. Making login synchronously call User Service to resolve
this would couple Auth Service's critical path to User Service's
uptime, undermining the "13 independently deployable services" premise
the rest of this doc is built on.

Decision: login keeps returning account_id: null / role: null, same
as today. The client (frontend, or anyone driving the API directly) is
expected to immediately exchange that for a real scoped token —
GET /api/accounts (or the equivalent user-accounts-listing endpoint,
Phase 4) to find the user's account(s), then POST /auth/issue-scoped-token
— before calling anything else. For the common individual-account case
(auto-created at signup, Phase 4) this is meant to happen automatically and
invisibly right after login, not as a user-facing step; it's the same
mechanism spec §4's Account Switcher uses, just triggered once by default
instead of only on manual switch.

This is enforced, not just documented: api-gateway's proxy rejects any
request to a non-auth route with a null account_id (403 account_scope_required, see app/api/proxy.py) — so a client can't
accidentally use an unscoped token against account-scoped data by skipping
the exchange step. Known gap: this guard doesn't yet account for
SuperAdmin, which spec §8 Service 13 describes as "platform-level, not
account-scoped" — when Phase 14 (Admin Service) lands, this guard needs an
exemption for admin-role tokens, which will also require deciding how a
SuperAdmin token gets minted without going through the account-scoping
flow at all.
## Diagram
_(Add a request-flow / event-flow diagram once the gateway + auth + one
downstream service exist end-to-end.)_