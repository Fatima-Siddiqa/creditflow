# Routes reachable with an identity-only token (account_id: null) — see
# docs/ARCHITECTURE.md "Login issues an identity-only token". These are
# exactly the routes whose entire job is to get the caller FROM an
# unscoped (or differently-scoped) token TO a correctly scoped one, or to
# look up what accounts even exist to scope to in the first place.
#
# This is a different list from PUBLIC_ROUTES (public_routes.py): entries
# here still require a valid, live JWT — verify_access_token already ran
# by the time this is checked (see app/api/proxy.py). This list only
# exempts a route from the *additional* "your token must already have a
# real account_id" check, not from authentication itself.
#
# Explicit allowlist, not a blocklist, for the same reason as
# PUBLIC_ROUTES: a newly added account-scoped route is locked down by
# default until someone deliberately opens it up.
#
# Exact-match entries have no path parameters. Entries with "*" match
# exactly one path segment in that position (not a full glob) — e.g.
# ("POST", "accounts/*/switch") matches "accounts/<uuid>/switch" but not
# "accounts/<uuid>/switch/extra".
ACCOUNT_SCOPE_EXEMPT_ROUTES: set[tuple[str, str]] = {
    ("POST", "accounts"),           # create a team account — independent of caller's current scope
    ("GET", "accounts/mine"),       # list accounts to switch between
    ("POST", "accounts/*/switch"),  # the actual switch — the whole point is working with an unscoped token
    ("POST", "invites/*/accept"),   # joining a NEW account; caller may not have a scoped token yet
}


def is_account_scope_exempt(method: str, path: str) -> bool:
    if (method, path) in ACCOUNT_SCOPE_EXEMPT_ROUTES:
        return True

    segments = path.split("/")
    for exempt_method, exempt_pattern in ACCOUNT_SCOPE_EXEMPT_ROUTES:
        if exempt_method != method:
            continue
        pattern_segments = exempt_pattern.split("/")
        if len(pattern_segments) != len(segments):
            continue
        if all(p == "*" or p == s for p, s in zip(pattern_segments, segments)):
            return True

    return False