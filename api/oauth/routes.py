import os
import logging
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from authlib.integrations.starlette_client import OAuth, OAuthError
from typing import Optional

logger = logging.getLogger(__name__)

# Set up templates
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "web"))

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

oauth = OAuth()

oauth.register(
    name="oidc",
    client_id=os.getenv("OIDC_CLIENT_ID"),
    client_secret=os.getenv("OIDC_CLIENT_SECRET"),
    server_metadata_url=os.getenv("OIDC_DISCOVERY_URL"),
    client_kwargs={"scope": os.getenv("OIDC_SCOPE", "openid profile email")},
)

@router.get("/login", response_class=HTMLResponse)
async def login(request: Request, redirect_uri: Optional[str] = None, return_url: Optional[str] = None):
    """
    Serve the login page or initiate OAuth flow based on the request.
    """
    # For AJAX/API requests, return the OAuth redirect
    if "application/json" in request.headers.get("accept", ""):
        redirect_uri = request.url_for("auth_callback")
        return await oauth.oidc.authorize_redirect(request, redirect_uri)
    
    # For browser requests, serve the auth.html page with return_url
    return templates.TemplateResponse("auth.html", {
        "request": request,
        "return_url": return_url or "/"
    })

@router.get("/logout")
async def logout(request: Request):
    """
    Logout the current user by clearing the session and authentication cookies.
    """
    # Create response
    response = RedirectResponse(url="/auth/login")
    
    # Clear the session if it exists
    if hasattr(request, 'session'):
        request.session.clear()
    
    from api.oauth.config import get_auth_config

    # Get the cookie remover function
    auth_config = get_auth_config(provider, platform)
    cookie_remover = auth_config.get_cookie_remover_func()

    # Use it to delete cookies
    if cookie_remover:
        cookie_config = cookie_remover()
        response.set_cookie(**cookie_config)
    
    # Clear the access token cookie
    response.delete_cookie('access_token', **cookie_kwargs)
    
    # Clear any other authentication-related cookies
    for cookie_name in ['refresh_token', 'session', 'session_id']:
        if cookie_name in request.cookies:
            response.delete_cookie(cookie_name, **cookie_kwargs)
    
    return response

@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    """
    Handle the OAuth callback after successful authentication.
    """
    try:
        token = await oauth.oidc.authorize_access_token(request)
        logger.info("OIDC token received")
        
        # For API requests, return JSON
        if "application/json" in request.headers.get("accept", ""):
            return {"message": "Authentication successful", "token": token}
            
        # For browser requests, redirect to the home page or original URL
        redirect_url = request.session.pop("next_url", "/")
        response = RedirectResponse(url=redirect_url)
        
        # Set the access token in a secure, HTTP-only cookie
        if "access_token" in token:
            response.set_cookie(
                key="access_token",
                value=f"Bearer {token['access_token']}",
                httponly=True,
                secure=not os.getenv("DEBUG", "").lower() in ("true", "1", "yes"),
                samesite="lax"
            )
            
        return response
        
    except OAuthError as exc:
        logger.error("OAuth error during callback: %s", exc)
        # For API requests, return JSON error
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=400, detail="OAuth authentication failed")
        # For browser requests, redirect to login with error
        return RedirectResponse(url=f"/auth/login?error={str(exc)}")
    except Exception as e:
        logger.error("Unexpected error during OAuth callback: %s", str(e))
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=500, detail="Internal server error")
        return RedirectResponse(url="/auth/login?error=internal_error")

