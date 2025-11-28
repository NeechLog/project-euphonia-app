import os
import time
import secrets
import logging

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth-google"])

_STATE_COOKIE_NAME = "g_oidc_state"
_STATE_SECRET = os.getenv("GOOGLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret"))
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600

_TOKEN_ENDPOINT = os.getenv("GOOGLE_TOKEN_ENDPOINT", "https://oauth2.googleapis.com/token")
_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


def _encode_state_cookie(state: str) -> str:
    now = int(time.time())
    payload = {"state": state, "iat": now, "exp": now + _STATE_TTL_SECONDS}
    return jwt.encode(payload, _STATE_SECRET, algorithm=_STATE_ALG)


def _decode_state_cookie(token: str) -> str:
    data = jwt.decode(token, _STATE_SECRET, algorithms=[_STATE_ALG])
    return data.get("state", "")


@router.get("/state")
async def issue_state(request: Request):
    state = secrets.token_urlsafe(32)
    signed = _encode_state_cookie(state)
    resp = JSONResponse({"state": state})
    resp.set_cookie(
        key=_STATE_COOKIE_NAME,
        value=signed,
        httponly=True,
        secure=False,  # set True in production with HTTPS
        samesite="lax",
        path="/",
    )
    return resp


def _exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
    if not _TOKEN_ENDPOINT or not _CLIENT_ID:
        raise RuntimeError("GOOGLE_TOKEN_ENDPOINT and GOOGLE_CLIENT_ID must be configured")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": _CLIENT_ID,
    }

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
        expected_state = _decode_state_cookie(cookie)
    except JWTError as exc:
        logger.warning("Invalid state cookie: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state cookie")

    if not expected_state or expected_state != state:
        logger.warning("State mismatch: expected %s, got %s", expected_state, state)
        raise HTTPException(status_code=400, detail="State mismatch")

    logger.info("Google OIDC callback received. code=%s, state=%s", code, state)

    if code:
        try:
            redirect_uri = str(request.url.replace(query=""))
            _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
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

    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri are required")

    tokens = _exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, code_verifier=code_verifier)
    return JSONResponse(tokens)
