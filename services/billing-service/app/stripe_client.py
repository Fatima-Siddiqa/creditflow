import stripe

from app.config import settings

stripe.api_key = settings.stripe_secret_key

PRICE_IDS = {"pro": settings.stripe_price_id_pro, "team": settings.stripe_price_id_team}


def create_customer(account_id) -> str:
    customer = stripe.Customer.create(metadata={"account_id": str(account_id)})
    return customer.id


def create_checkout_session(stripe_customer_id: str, plan_tier: str, success_url: str, cancel_url: str) -> str:
    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        mode="subscription",
        line_items=[{"price": PRICE_IDS[plan_tier], "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan_tier": plan_tier},       
        subscription_data={"metadata": {"plan_tier": plan_tier}},
    )
    return session.url


def update_subscription_plan(stripe_subscription_id: str, new_plan_tier: str) -> dict:
    subscription = stripe.Subscription.retrieve(stripe_subscription_id)
    item_id = subscription["items"]["data"][0]["id"]
    updated = stripe.Subscription.modify(
        stripe_subscription_id,
        items=[{"id": item_id, "price": PRICE_IDS[new_plan_tier]}],
        proration_behavior="create_prorations",
    )
    return updated


def create_refund(stripe_invoice_id: str, reason: str | None) -> dict:
    invoice = stripe.Invoice.retrieve(stripe_invoice_id)
    payment_intent = invoice["payment_intent"]
    refund = stripe.Refund.create(payment_intent=payment_intent, reason="requested_by_customer" if reason else None)
    return refund