# Definition of Done

Every functional bullet in the spec (point 8, all 13 services) must be fully
implemented — this checklist is the integration-level acceptance bar on
top of that, not a reduced scope.

Mandatory bonus items (same weight as core):
- [ ] Image Publishing to LinkedIn
- [ ] Recurring schedules

AWS deployment and AI image generation are optional stretch, not required.

## Checklist
- [ ] All 13 backend services run independently via docker-compose with
      their own database/schema, alongside the frontend application.
- [ ] Signup → email verification → login → account creation flow works
      end-to-end.
- [ ] Forgot-password OTP flow works end-to-end by email.
- [ ] A user can purchase credits via Stripe sandbox checkout and see
      balance update.
- [ ] A user can list credits for sale and another account can purchase
      them via the marketplace.
- [ ] An AI generation request streams tokens live to the frontend via SSE
      and deducts credits correctly.
- [ ] A piece of content can be placed on the calendar via the Scheduler
      Service and is published to a connected LinkedIn sandbox/test account
      at the scheduled time.
- [ ] Recurring schedules work (weekly/cadence-based).
- [ ] Image-attached posts publish as text+image via LinkedIn's Images API.
- [ ] At least one scraper job runs and stores data usable by the content
      flow.
- [ ] Owner, Member, and SuperAdmin each see their correct, distinct set of
      frontend pages, enforced by role.
- [ ] Admin console shows active sessions, per-account usage, and an audit
      log of recent events.
- [ ] All inter-service events survive a forced restart of a consumer
      without data loss or duplication.
- [ ] README documents the architecture, setup steps, and any AWS
      free-tier constraints/tradeoffs made (if deployment attempted).