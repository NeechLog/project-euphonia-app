import os
import time
import secrets
import logging

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests

from api.oauth.config import get_auth_config


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth-google"])

_STATE_COOKIE_NAME = "g_oidc_state"
_STATE_SECRET = os.getenv("GOOGLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret"))
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600


def _normalize_platform(value: str | None) -> str:
    """Normalize platform name to lowercase, defaulting to 'web'."""
    return (value or "web").lower()


def get_platform_config(platform: str) -> dict:
    """
    Get Google OAuth configuration for the specified platform.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        dict: Configuration containing Google OAuth parameters
        
    Raises:
        HTTPException: If configuration is not found or invalid
    """
    try:
        cfg = get_auth_config("google", platform)
        return {
            "platform": platform,
            "client_id": cfg.client_id,
            "authorization_endpoint": cfg.authorization_endpoint,
            "token_endpoint": cfg.token_endpoint,
            "scope": cfg.scope,
            "redirect_uri": cfg.redirect_uri,
        }
    except Exception as e:
        logger.error(f"Failed to load Google config for platform '{platform}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Google authentication is not properly configured for platform '{platform}'"
        )


@router.get("/config")
async def get_client_config(platform: str):
    """
    Get Google OAuth configuration for the specified platform.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        JSON: Configuration containing Google OAuth parameters
    """
    platform = _normalize_platform(platform)
    return get_platform_config(platform)


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


@router.get("/state")
async def issue_state(request: Request):
    platform = _normalize_platform(request.query_params.get("platform"))
    get_platform_config(platform)  # validate config exists

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


def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    client_config: dict,
    code_verifier: str | None = None,
) -> dict:
    token_endpoint = client_config.get("token_endpoint")
    if not token_endpoint:
        raise RuntimeError("Google token endpoint must be configured")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_config["client_id"],
    }

    if client_config.get("client_secret"):
        data["client_secret"] = client_config["client_secret"]

    if code_verifier:
        data["code_verifier"] = code_verifier

    resp = requests.post(token_endpoint, data=data, timeout=10)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}

    if not resp.ok:
        logger.error("Google token endpoint error: %s", payload)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google token endpoint error")

    logger.info("Google OIDC token response: %s", payload)
    return payload


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
        logger.warning("State mismatch: expected %s, got %s", expected_state, state)
        raise HTTPException(status_code=400, detail="State mismatch")

    config = _get_platform_config(platform)
    logger.info("Google OIDC callback received. code=%s, state=%s", code, state)

    if code:
        try:
            redirect_uri = str(request.url.replace(query=""))
            _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, client_config=config)
        except Exception as exc:
            logger.error("Google server-side code exchange failed: %s", exc, exc_info=True)

    html = """<!DOCTYPE html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Login complete</title></head>
  <body style=\"font-family: sans-serif; text-align: center; margin-top: 3rem;\">
    <h1>Google authentication completed</h1>
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

    config = _get_platform_config(platform)
    tokens = _exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        client_config=config,
        code_verifier=code_verifier,
    )
    return JSONResponse(tokens)
