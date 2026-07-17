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
| `account_events` | user-service | `account.created`, `account.updated`, `member.joined` |
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

## Outbox pattern and idempotent consumers
_(added next)_

## Note on early-phase publishing
An exchange can exist and receive published messages before any
consumer's phase has been built — this is expected, not a bug. A message
published to an exchange with no bound queue isn't retained anywhere
(RabbitMQ has nowhere to put it). Don't mistake "no queue yet" for
"publish failed" — check the exchange's publish count in the management
UI (Exchanges tab), not queue depth, to confirm a service is publishing
correctly ahead of its consumers existing.