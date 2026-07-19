# CreditFlow — Event Contracts

## Envelope
Every event published to RabbitMQ, regardless of producer, uses this shape:

\`\`\`json
{
  "event_id": "uuid",
  "event_type": "invoice.paid",
  "occurred_at": "2026-07-13T10:00:00Z",
  "account_id": "uuid-or-null",
  "producer": "billing-service",
  "schema_version": 1,
  "payload": { }
}
\`\`\`

- `event_id`: unique per event, used by consumers for idempotency (see below).
- `account_id`: nullable — a few events (e.g. `scrape.completed`) aren't account-scoped.
- `schema_version`: lets a consumer branch/reject on payload shape changes.

## Exchange topology
Topic exchanges, one per domain, routing key = `event_type`. All durable,
publisher confirms required, `delivery_mode=2`.

| Exchange | Publisher | Event types |
|---|---|---|
| `identity_events` | auth-service | `user.registered`, `user.logged_in`, `user.password_reset_requested` |
| `account_events` | user-service | `account.created`, `account.updated`, `member.joined`, `invite.created` |
| `billing_events` | billing-service | `invoice.paid`, `payment.failed`, `subscription.updated`, `subscription.downgraded`, `refund.issued` |
| `credits_events` | credits-service | `credits.credited`, `credits.debited`, `credits.low_balance` |
| `usage_events` | usage-service | `usage.threshold_reached` |
| `ai_events` | ai-generation-service | `ai.generation_completed`, `ai.generation_failed` |
| `content_events` | content-service, scheduler-service | `content.created`, `content.updated`, `content.scheduled` |
| `social_events` | social-publishing-service | `post.published`, `post.failed` |
| `scraper_events` | scraper-service | `scrape.completed`, `scrape.failed`, `scrape.requested` |
| `notification_events` | notification-service | `notification.sent` |

Each consumer declares one durable queue and binds it to only the routing
keys it needs (multiple bindings per queue, not one queue per event type).
`admin-service` is the exception — it binds `#` on every exchange for the
audit log.

## Webhook relay events (api-gateway)
In addition to the producers listed above, `api-gateway` also publishes
onto `billing_events`, `social_events`, and `ai_events` — as a relay for
verified, deduped inbound webhooks (Stripe, LinkedIn, OpenRouter
respectively). Per spec §8 Service 1's own event contract: *"Publishes:
billing.\*, social.\*, ai.\* (relayed from webhooks)."* The gateway does
NOT interpret the webhook's business meaning — it verifies the signature,
dedups by event ID, and republishes the raw payload for the owning
service to process. This is also how spec §8 Service 4 (Billing)'s
*"Persist every Stripe webhook event received (via Gateway)..."*
requirement is satisfied: billing-service receives Stripe's payload via
this relayed event, not a direct synchronous call from the gateway.

| Exchange | Event type | Payload |
|---|---|---|
| `billing_events` | `billing.webhook_received` | `{"source": "stripe", "raw_event": {...}}` |
| `social_events` | `social.webhook_received` | `{"source": "linkedin", "raw_event": {...}}` |
| `ai_events` | `ai.webhook_received` | `{"source": "openrouter", "raw_event": {...}}` |

**Note on LinkedIn/OpenRouter:** as of Phase 3, neither product has a
confirmed real inbound-webhook mechanism for what this project actually
integrates with (LinkedIn's Sign-In/Share products are outbound-only from
our side; OpenRouter's completions API is synchronous, not webhook-based).
These two endpoints exist to satisfy spec §8 Service 1's literal
requirement (no hedge in the PDF) and use a generic HMAC-signature
scaffold pending confirmation from the mentor on whether/how a real
signed payload would ever arrive here. Revisit when Phase 11 (Social
Publishing) is built and LinkedIn's actual integration surface is known.

## `invoice.paid` payload shape (assumed — Billing Service doesn't exist yet)
User/Tenant Service (Phase 4) consumes `invoice.paid` from `billing_events`
to update `accounts.plan_tier` (`services/user-service/app/events/billing_consumer.py`).
Since Billing Service (Phase 5) hasn't been built, this is this project's
own documented **assumption** about what it will eventually publish, not a
contract confirmed against real producer code — Phase 5's own handoff note
says to pin this down before moving to Phase 6, so this is that.

```json
{
  "account_id": "uuid",
  "plan_tier": "free | pro | team",
  "amount": 2900
}
```

- `account_id`: required. If it doesn't match an existing `accounts` row,
  the consumer raises rather than silently no-op'ing — see
  `apply_invoice_paid`'s docstring for why that's deliberate.
- `plan_tier`: required, written directly to `accounts.plan_tier`.
- `amount`: present for Credits Service's benefit (Phase 6, "Consumes:
  `invoice.paid`... to credit an account's balance"); User/Tenant Service
  doesn't read it.
- **Not included:** anything about seat count/limits. `accounts.seat_count`
  isn't a stored column (it's `COUNT(*)` over `account_members`), so
  there's nothing for this event to adjust there — if Phase 5 or 6 need
  plan-tier-based seat limits, that's a new decision and a new column, not
  something this phase's data model already supports.

**When Phase 5 is actually built:** if the real payload differs from this,
update this section to match reality, not the other way around — this
block is describing an assumption a consumer was built against, not a
requirement Billing Service is bound by.

## Idempotent consumers
Every consuming service owns a `processed_events(event_id UUID PRIMARY KEY,
processed_at TIMESTAMPTZ)` table in its own schema. The check-and-insert
happens in the *same transaction* as the business-logic write it guards —
see `services/user-service/app/events/identity_consumer.py`'s
`create_account_for_registered_user` for the reference implementation
every later consumer (billing, credits, usage, content, scheduler...)
should copy:

\`\`\`python
inserted = db.execute(
    text("INSERT INTO <schema>.processed_events (event_id) VALUES (:id) "
         "ON CONFLICT DO NOTHING RETURNING event_id"),
    {"id": event_id},
).fetchone()
if inserted is None:
    return  # already handled
# ... business logic, same transaction ...
\`\`\`

## Consumer retry / DLQ pattern
Every consumer queue is declared with `x-dead-letter-exchange` pointing at
a `<queue-name>.dlx` fanout exchange, bound to a `<queue-name>.dlq` durable
queue. On a processing failure, the message is republished to its own
source exchange with an incremented `x-retry-count` header (up to 3
attempts) rather than requeued in place — this avoids a tight
requeue/fail busy-loop against a broker that has no built-in delay. After
the retry budget is exhausted, the message is rejected with
`requeue=False`, which the queue's DLX configuration routes to its DLQ.
See `identity_consumer.py`'s `_process_message` for the reference
implementation.

## Outbox pattern
Deferred to billing-service (PR set for Phase 5) and credits-service —
neither exists yet. See the original phase-planning doc for the pattern;
it'll be documented here for real once billing-service implements it.

## Note on early-phase publishing
An exchange can exist and receive published messages before any
consumer's phase has been built — this is expected, not a bug. A message
published to an exchange with no bound queue isn't retained anywhere
(RabbitMQ has nowhere to put it). Don't mistake "no queue yet" for
"publish failed" — check the exchange's publish count in the management
UI (Exchanges tab), not queue depth, to confirm a service is publishing
correctly ahead of its consumers existing.