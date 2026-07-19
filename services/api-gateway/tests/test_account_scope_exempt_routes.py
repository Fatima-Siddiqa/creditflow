from app.account_scope_exempt_routes import is_account_scope_exempt


def test_exact_match_routes_are_exempt():
    assert is_account_scope_exempt("POST", "accounts") is True
    assert is_account_scope_exempt("GET", "accounts/mine") is True


def test_wildcard_routes_are_exempt():
    assert is_account_scope_exempt("POST", "accounts/0e8fe180-c1ea-4a1f-bbca-8bc6f68ce470/switch") is True
    assert is_account_scope_exempt("POST", "invites/some-raw-token/accept") is True


def test_wildcard_does_not_match_extra_segments():
    assert is_account_scope_exempt("POST", "accounts/some-id/switch/extra") is False


def test_similar_but_non_exempt_routes_are_not_exempt():
    # same resource family, different action — must still require scoping
    assert is_account_scope_exempt("GET", "accounts/some-id") is False
    assert is_account_scope_exempt("POST", "accounts/some-id/invites") is False
    assert is_account_scope_exempt("PATCH", "accounts/some-id/members/some-user") is False


def test_wrong_method_is_not_exempt():
    # exempt as POST, not GET — a GET to the same path must still be checked
    assert is_account_scope_exempt("GET", "accounts/some-id/switch") is False