import os
import time
import secrets
import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests

from api.oauth.config import get_auth_config


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/apple", tags=["auth-apple"])

_STATE_COOKIE_NAME = "a_oidc_state"
_STATE_SECRET = os.getenv("APPLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret"))
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600


def _normalize_platform(value: str | None) -> str:
    """Normalize platform name to lowercase, defaulting to 'web'."""
    return (value or "web").lower()


def _get_platform_client_config(platform: str) -> dict:
    """
    Get Apple OAuth configuration for the specified platform.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        dict: Configuration containing Apple-specific parameters
        
    Raises:
        HTTPException: If configuration is not found or invalid
    """
    try:
        return get_auth_config("apple", platform)
    except Exception as e:
        logger.error(f"Failed to load Apple config for platform '{platform}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Apple authentication is not properly configured for platform '{platform}'"
        )


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


def _load_apple_private_key(auth_key_path: str) -> str:
    """
    Load the Apple private key from the specified path.
    
    Args:
        auth_key_path: Path to the .p8 private key file
        
    Returns:
        str: The contents of the private key file
        
    Raises:
        HTTPException: If the key file cannot be read or is not found
    """
    try:
        path = Path(auth_key_path)
        if not path.exists():
            raise FileNotFoundError(f"Apple auth key file not found at {auth_key_path}")
        return path.read_text()
    except Exception as e:
        logger.error(f"Failed to load Apple private key: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load Apple authentication key. Please check the configuration."
        )


def _build_apple_client_secret(client_cfg) -> str:
    """Build Apple client secret JWT using ES256 and your .p8 key."""
    if not (client_cfg.client_id and client_cfg.team_id and client_cfg.key_id and client_cfg.auth_key_path):
        raise RuntimeError("Apple config incomplete (client_id/team_id/key_id/auth_key_path)")

    now = int(time.time())
    claims = {
        "iss": client_cfg.team_id,
        "iat": now,
        "exp": now + 1800,
        "aud": "https://appleid.apple.com",
        "sub": client_cfg.client_id,
    }
    headers = {"kid": client_cfg.key_id}
    private_key = _load_apple_private_key(client_cfg.auth_key_path)
    return jwt.encode(claims, private_key, algorithm="ES256", headers=headers)


def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    client_cfg,
    code_verifier: str | None = None,
) -> dict:
    token_endpoint = client_cfg.token_endpoint
    if not token_endpoint:
        raise RuntimeError("APPLE_TOKEN_ENDPOINT must be configured")

    client_secret = _build_apple_client_secret(client_cfg)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_cfg.client_id,
        "client_secret": client_secret,
    }

    if code_verifier:
        data["code_verifier"] = code_verifier

    resp = requests.post(token_endpoint, data=data, timeout=10)
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
    _get_platform_client_config(platform)

    state = secrets.token_urlsafe(32)
    signed = _encode_state_cookie(state, platform)
    resp = JSONResponse({"state": state, "platform": platform})
    resp.set_cookie(
        key=_STATE_COOKIE_NAME,
        value=signed,
        httponly=True,
        secure=True,
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

    client_cfg = _get_platform_client_config(platform)
    logger.info("Apple OIDC callback received. code=%s, state=%s", code, state)

    if code:
        try:
            redirect_uri = str(request.url.replace(query=""))
            _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, client_cfg=client_cfg)
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

    client_cfg = _get_platform_client_config(platform)
    tokens = _exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        client_cfg=client_cfg,
        code_verifier=code_verifier,
    )
    return JSONResponse(tokens)
