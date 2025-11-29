import os
import time
import secrets
import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/apple", tags=["auth-apple"])

_STATE_COOKIE_NAME = "a_oidc_state"
_STATE_SECRET = os.getenv("APPLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret"))
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600

_TOKEN_ENDPOINT = os.getenv("APPLE_TOKEN_ENDPOINT", "https://appleid.apple.com/auth/token")
_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
_KEY_ID = os.getenv("APPLE_KEY_ID", "")
_AUTH_KEY_PATH = os.getenv("APPLE_AUTH_KEY_PATH", "")  # path to AuthKey_XXXX.p8
_SUPPORTED_PLATFORMS = {"web", "ios", "android"}


def _normalize_platform(value: str | None) -> str:
    platform = (value or "web").lower()
    if platform not in _SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported Apple platform '{platform}'")
    return platform


def _get_platform_client_id(platform: str) -> str:
    suffix = platform.upper()
    client_id = os.getenv(f"APPLE_CLIENT_ID_{suffix}") or os.getenv("APPLE_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=500, detail=f"Apple client ID not configured for platform '{platform}'")
    return client_id


def _encode_state_cookie(state: str, platform: str) -> str:
    now = int(time.time())
    payload = {
        "state": state,
        "platform": platform,
        "iat": now,
        "exp": now + _STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, _STATE_SECRET, algorithm=_STATE_ALG)


def _decode_state_cookie(token: str) -> dict:
    return jwt.decode(token, _STATE_SECRET, algorithms=[_STATE_ALG])


def _load_apple_private_key() -> str:
    if not _AUTH_KEY_PATH:
        raise RuntimeError("APPLE_AUTH_KEY_PATH must be configured")
    path = Path(_AUTH_KEY_PATH)
    return path.read_text()


def _build_apple_client_secret(client_id: str) -> str:
    """Build Apple client secret JWT using ES256 and your .p8 key."""
    if not (client_id and _TEAM_ID and _KEY_ID):
        raise RuntimeError("APPLE_CLIENT_ID_{PLATFORM}, APPLE_TEAM_ID and APPLE_KEY_ID must be configured")

    now = int(time.time())
    claims = {
        "iss": _TEAM_ID,
        "iat": now,
        "exp": now + 1800,
        "aud": "https://appleid.apple.com",
        "sub": client_id,
    }
    headers = {"kid": _KEY_ID}
    private_key = _load_apple_private_key()
    return jwt.encode(claims, private_key, algorithm="ES256", headers=headers)


def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    client_id: str,
    code_verifier: str | None = None,
) -> dict:
    if not _TOKEN_ENDPOINT:
        raise RuntimeError("APPLE_TOKEN_ENDPOINT must be configured")

    client_secret = _build_apple_client_secret(client_id)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if code_verifier:
        data["code_verifier"] = code_verifier

    resp = requests.post(_TOKEN_ENDPOINT, data=data, timeout=10)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}

    if not resp.ok:
        logger.error("Apple token endpoint error: %s", payload)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Apple token endpoint error")

    logger.info("Apple OIDC token response: %s", payload)
    return payload


@router.get("/state")
async def issue_state(request: Request):
    platform = _normalize_platform(request.query_params.get("platform"))
    _get_platform_client_id(platform)

    state = secrets.token_urlsafe(32)
    signed = _encode_state_cookie(state, platform)
    resp = JSONResponse({"state": state, "platform": platform})
    resp.set_cookie(
        key=_STATE_COOKIE_NAME,
        value=signed,
        httponly=True,
        secure=False,  # set True in production with HTTPS
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/callback")
async def callback(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")

    if not state:
        raise HTTPException(status_code=400, detail="Missing state in callback")

    cookie = request.cookies.get(_STATE_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=400, detail="Missing state cookie")

    try:
        state_payload = _decode_state_cookie(cookie)
    except JWTError as exc:
        logger.warning("Invalid state cookie: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state cookie")

    expected_state = state_payload.get("state")
    platform = state_payload.get("platform", "web")

    if not expected_state or expected_state != state:
        logger.warning("Apple state mismatch: expected %s, got %s", expected_state, state)
        raise HTTPException(status_code=400, detail="State mismatch")

    client_id = _get_platform_client_id(platform)
    logger.info("Apple OIDC callback received. code=%s, state=%s", code, state)

    if code:
        try:
            redirect_uri = str(request.url.replace(query=""))
            _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, client_id=client_id)
        except Exception as exc:
            logger.error("Apple server-side code exchange failed: %s", exc, exc_info=True)

    html = """<!DOCTYPE html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Login complete</title></head>
  <body style=\"font-family: sans-serif; text-align: center; margin-top: 3rem;\">
    <h1>Apple authentication completed</h1>
    <p>You may now return to the application.</p>
  </body>
</html>"""
    return HTMLResponse(content=html)


@router.post("/exchange")
async def exchange_from_client(request: Request):
    body = await request.json()
    code = body.get("code")
    code_verifier = body.get("code_verifier")
    redirect_uri = body.get("redirect_uri")
    platform = _normalize_platform(body.get("platform"))

    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri are required")

    client_id = _get_platform_client_id(platform)
    tokens = _exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        client_id=client_id,
        code_verifier=code_verifier,
    )
    return JSONResponse(tokens)
