import os
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth, OAuthError


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/auth", tags=["auth"])


oauth = OAuth()


oauth.register(
    name="oidc",
    client_id=os.getenv("OIDC_CLIENT_ID"),
    client_secret=os.getenv("OIDC_CLIENT_SECRET"),
    server_metadata_url=os.getenv("OIDC_DISCOVERY_URL"),
    client_kwargs={"scope": os.getenv("OIDC_SCOPE", "openid profile email")},
)


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except OAuthError as exc:
        logger.error("OAuth error during callback: %s", exc)
        raise HTTPException(status_code=400, detail="OAuth authentication failed")

    logger.info("OIDC token received: %s", token)

    return JSONResponse({"message": "Authentication successful", "token_received": True})

