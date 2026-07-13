# CreditFlow — Event Contracts

**Not written yet — this is Phase 1's deliverable.**

Phase 1 will define here: the event envelope format (event_id, event_type,
occurred_at, account_id, payload, etc.), the RabbitMQ exchange/queue
topology (which service publishes/consumes what, DLQ setup, retry counts),
the transactional outbox pattern (used by billing-service), and the
idempotent-consumer pattern (`processed_events` table) that every consumer
implements identically.

Do not start writing service code before this file is filled in.