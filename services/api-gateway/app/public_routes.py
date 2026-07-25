# Routes that don't require a valid access token. Explicit allowlist, not a
# blocklist — anything NOT listed here is protected by default. That's the
# safer failure mode: a newly added downstream route is locked down until
# someone deliberately opens it up, rather than silently public until
# someone remembers to add a check.
#
# Only auth-service's identity-bootstrapping routes are here. You can't
# require a token to sign up, log in, verify your email, or request/reset
# a forgotten password — and /refresh's entire purpose is working when the
# access token is no longer valid, so it can't require one either.
# auth-service's own /logout is deliberately NOT here: it depends on
# `current_user`'s jti server-side (services/auth-service/app/api/auth.py)
# to know which session to revoke, so it's protected like everything else.
# social/linkedin/callback is here for the same reason as auth-service's
# routes above: LinkedIn's redirect is a plain browser navigation with no
# Authorization header at all. Account context comes from `state`
# (set to account_id in /social/linkedin/connect), not a JWT.
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "auth/signup"),
    ("POST", "auth/verify-email"),
    ("POST", "auth/login"),
    ("POST", "auth/refresh"),
    ("POST", "auth/forgot-password"),
    ("POST", "auth/reset-password"),
    ("GET", "social/linkedin/callback"),
}


def is_public_route(method: str, path: str) -> bool:
    return (method, path) in PUBLIC_ROUTES