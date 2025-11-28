"""Deprecated generic stateless auth module.

Provider-specific implementations now live in:

* oauth.google_stateless
* oauth.apple_stateless

This file is kept only to avoid import errors; do not use it for new code.
"""

from fastapi import APIRouter


router = APIRouter()


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE_NAME = "oidc_state"
_STATE_SECRET = os.getenv("STATE_SECRET_KEY", "change-me-state-secret")
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600

_TOKEN_ENDPOINT = os.getenv("OIDC_TOKEN_ENDPOINT", "")
_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")


def _encode_state_cookie(state: str) -> str:
    now = int(time.time())
    payload = {"state": state, "iat": now, "exp": now + _STATE_TTL_SECONDS}
    return jwt.encode(payload, _STATE_SECRET, algorithm=_STATE_ALG)


def _decode_state_cookie(token: str) -> str:
    data = jwt.decode(token, _STATE_SECRET, algorithms=[_STATE_ALG])
    return data.get("state", "")


@router.get("/state")
async def issue_state(request: Request):
    """Issue a fresh OIDC state and set it as a signed cookie.

    Response JSON contains the raw state value for the client to include
    in the authorization request. The cookie is used by the callback to
    validate that the state round-tripped correctly.
    """
    # state = secrets.token_urlsafe(32)
    # signed = _encode_state_cookie(state)
    # resp = JSONResponse({"state": state})
    # resp.set_cookie(
    #     key=_STATE_COOKIE_NAME,
    #     value=signed,
    #     httponly=True,
    #     secure=False,  # consider True with HTTPS
    #     samesite="lax",
    #     path="/",
    # )
    # return resp
    pass
        value=signed,
        httponly=True,
        secure=False,  # consider True with HTTPS
        samesite="lax",
        path="/",
    )
    return resp


def _exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
    if not _TOKEN_ENDPOINT or not _CLIENT_ID:
        raise RuntimeError("OIDC_TOKEN_ENDPOINT and OIDC_CLIENT_ID must be configured")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": _CLIENT_ID,
    }

    # For public PKCE clients, client_secret is typically omitted.
    if _CLIENT_SECRET:
        data["client_secret"] = _CLIENT_SECRET

    if code_verifier:
        data["code_verifier"] = code_verifier

    resp = requests.post(_TOKEN_ENDPOINT, data=data, timeout=10)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}

    if not resp.ok:
        logger.error("Token endpoint error: %s", payload)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token endpoint returned an error",
        )

    logger.info("OIDC token response: %s", payload)
    return payload


@router.get("/callback")
async def callback(request: Request):
    """OIDC redirect URI.

    Validates CSRF state using the signed cookie. For now, it just logs
    the received parameters and returns a simple HTML page; you can later
    add code-exchange with the token endpoint if desired.
    """
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")

    if not state:
        raise HTTPException(status_code=400, detail="Missing state in callback")

    cookie = request.cookies.get(_STATE_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=400, detail="Missing state cookie")

    try:
        expected_state = _decode_state_cookie(cookie)
    except JWTError as exc:
        logger.warning("Invalid state cookie: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state cookie")

    if not expected_state or expected_state != state:
        logger.warning("State mismatch: expected %s, got %s", expected_state, state)
        raise HTTPException(status_code=400, detail="State mismatch")

    logger.info("OIDC callback received. code=%s, state=%s", code, state)

    token_payload: dict | None = None
    if code:
        try:
            redirect_uri = str(request.url.replace(query=""))
            token_payload = _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
        except Exception as exc:
            logger.error("Server-side code exchange failed: %s", exc, exc_info=True)

    html = """<!DOCTYPE html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Login complete</title></head>
  <body style=\"font-family: sans-serif; text-align: center; margin-top: 3rem;\">
    <h1>Authentication completed</h1>
    <p>You may now return to the application.</p>
  </body>
</html>"""
    return HTMLResponse(content=html)


@router.post("/exchange")
async def exchange_from_client(request: Request):
    """Alternate path: browser posts code + code_verifier for token exchange.

    This allows a more explicit flow where the callback page's JS sends an
    API request carrying the authorization code and PKCE verifier. The
    server exchanges and logs the tokens without persisting them.
    """
    body = await request.json()
    code = body.get("code")
    code_verifier = body.get("code_verifier")
    redirect_uri = body.get("redirect_uri")

    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri are required")

    tokens = _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, code_verifier=code_verifier)
    return JSONResponse(tokens)
