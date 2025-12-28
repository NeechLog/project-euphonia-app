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
    
    from api.oauth.config import _auth_config

    # Get the cookie remover function
    cookie_remover = _auth_config.get_cookie_remover_func()

    # Use it to delete cookies
    if cookie_remover:
        cookie_config = cookie_remover()
        response.set_cookie(**cookie_config)
    
    # Clear the access token cookie
    response.delete_cookie('access_token', path="/")
    return response
