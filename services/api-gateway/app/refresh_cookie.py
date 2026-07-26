import json

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/auth"

# auth-service's /refresh and /logout expect refresh_token in the JSON
# body (RefreshRequest/LogoutRequest schemas) -- but per spec §4, the
# frontend never holds it in JS-readable form once it's an httpOnly
# cookie. The gateway is the only place that can bridge this.
INJECT_FROM_COOKIE_ROUTES = {"auth/refresh", "auth/logout"}
SET_COOKIE_ROUTES = {"auth/login", "auth/refresh"}
CLEAR_COOKIE_ROUTES = {"auth/logout"}


def inject_refresh_token_from_cookie(path: str, body: bytes, cookie_value: str | None) -> bytes:
    """Reads the httpOnly cookie and stitches it into the outgoing request
    body before forwarding downstream, since the browser itself has no
    access to the raw value to put there."""
    if path not in INJECT_FROM_COOKIE_ROUTES or not cookie_value:
        return body
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {}
    data["refresh_token"] = cookie_value
    return json.dumps(data).encode()


def extract_and_strip_refresh_token(path: str, body: bytes) -> tuple[bytes, str | None]:
    """For /login and /refresh responses: pulls refresh_token out of
    auth-service's JSON body so it can be set as an httpOnly cookie
    instead of handed to the browser in a JS-readable response body."""
    if path not in SET_COOKIE_ROUTES:
        return body, None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body, None
    token = data.pop("refresh_token", None)
    if token is None:
        return body, None
    return json.dumps(data).encode(), token