import os
import time
import secrets
import logging
from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests

from api.oauth.config import get_auth_config
from api.oauth.base_oauth import OAuthProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth-google"])

# Initialize the OAuth provider
_OAUTH_PROVIDER = OAuthProvider(
    provider_name="Google",
    state_cookie_name="g_oidc_state",
    state_secret=os.getenv("GOOGLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret")),
    state_ttl_seconds=600
)


def _normalize_platform(value: str | None) -> str:
    """Normalize platform name to lowercase, defaulting to 'web'."""
    normalized = (value or "web").lower()
    logger.debug("Normalized platform from '%s' to '%s'", value, normalized)
    return normalized


def get_platform_config(platform: str, include_secrets: bool = False) -> dict:
    """
    Get Google OAuth configuration for the specified platform.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        include_secrets: Whether to include sensitive information like client_secret
        
    Returns:
        dict: Configuration containing Google OAuth parameters
        
    Raises:
        HTTPException: If configuration is not found or invalid
    """
    logger.debug("Loading Google OAuth config for platform: %s (include_secrets=%s)", 
                platform, include_secrets)
    try:
        cfg = get_auth_config("google", platform)
        config = {
            "platform": platform,
            "client_id": cfg.client_id,
            "authorization_endpoint": cfg.authorization_endpoint,
            "token_endpoint": cfg.token_endpoint,
            "scope": cfg.scope,
            "redirect_uri": cfg.redirect_uri,
        }
        
        logger.debug("Loaded base Google OAuth config for platform: %s", platform)
        
        # Only include client_secret for internal server calls
        if include_secrets and hasattr(cfg, 'client_secret'):
            config["client_secret"] = cfg.client_secret
            
        return config
    except Exception as e:
        logger.error("Failed to load Google config for platform '%s': %s", 
                    platform, str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Google authentication is not properly configured for platform '{platform}'"
        )


def _get_internal_config(platform: str) -> dict:
    """
    Get Google OAuth configuration including sensitive information for internal use only.
    This should only be used by server-side components that need the client_secret.
    """
    logger.debug("Loading internal Google OAuth config for platform: %s", platform)
    try:
        config = get_platform_config(platform, include_secrets=True)
        logger.debug("Successfully loaded internal config for platform: %s", platform)
        return config
    except Exception as e:
        logger.error("Failed to load internal Google config for platform '%s': %s", 
                    platform, str(e), exc_info=True)
        raise


@router.get("/config")
async def get_client_config(platform: str):
    """
    Get Google OAuth configuration for the specified platform.
    This endpoint is safe to expose to clients as it doesn't return sensitive information.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        JSON: Configuration containing Google OAuth parameters (without sensitive data)
    """
    logger.info("Client config requested for platform: %s", platform)
    try:
        platform = _normalize_platform(platform)
        config = get_platform_config(platform, include_secrets=False)
        logger.debug("Returning client config for platform: %s", platform)
        return config
    except HTTPException as he:
        logger.warning("Client config request failed for platform '%s': %s", 
                      platform, he.detail)
        raise
    except Exception as e:
        logger.error("Unexpected error in get_client_config for platform '%s': %s", 
                    platform, str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while retrieving OAuth configuration"
        )


@router.get("/state")
async def issue_state(request: Request):
    """
    Issue a new OAuth state token for CSRF protection.
    
    Args:
        request: The incoming request containing the platform parameter
        
    Returns:
        JSONResponse: Contains the state token and related data
    """
    logger.info("State token requested")
    try:
        platform = request.query_params.get("platform")
        if not platform:
            logger.warning("State request missing required 'platform' parameter")
            raise HTTPException(
                status_code=400,
                detail="Missing required parameter: platform"
            )
            
        logger.debug("Validating platform config for: %s", platform)
        get_platform_config(platform)  # Validate platform config exists

        logger.info("Generating new state token for platform: %s", platform)
        state_data = _OAUTH_PROVIDER.create_state_response(request,platform)
        
        logger.debug("Successfully generated state token")
        
        # Create response with state data
        response_data = {
            "state": state_data["state"],
            "platform": state_data["platform"]
        }
        
        # Create JSON response
        response = JSONResponse(content=response_data)
        
        # Set the state cookie
        response.set_cookie(
            key=_OAUTH_PROVIDER.state_cookie_name,
            value=state_data["signed_state"],
            httponly=True,
            secure=True,
            samesite="lax",
            path="/"
        )
        
        logger.debug("Successfully set state cookie")
        return response
        
    except HTTPException as he:
        logger.warning("State token generation failed: %s (status_code=%d)", 
                      str(he.detail), he.status_code)
        raise
    except Exception as e:
        logger.error("Unexpected error in issue_state: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while generating the state token"
        )


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
    """Handle OAuth callback from Google."""
    async def exchange_callback(code: str, redirect_uri: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        return _exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            client_config=config
        )
    
    return await _OAUTH_PROVIDER.handle_callback(
        request=request,
        exchange_callback=exchange_callback,
        success_html_title="Google Login Complete",
        success_html_heading="Google authentication completed",
        config_loader=_get_internal_config
    )


@router.post("/exchange")
async def exchange_from_client(request: Request):
    body = await request.json()
    code = body.get("code")
    code_verifier = body.get("code_verifier")
    redirect_uri = body.get("redirect_uri")
    platform = _normalize_platform(body.get("platform"))

    if not all([code, redirect_uri, platform]):
        raise HTTPException(
            status_code=400,
            detail="Missing required parameters: code, redirect_uri, or platform"
        )

    try:
        config = _get_internal_config(platform)
        tokens = await _exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            client_config=config,
            code_verifier=code_verifier
        )
        return tokens
    except Exception as e:
        logger.error("Token exchange failed: %s", str(e))
        raise HTTPException(status_code=400, detail="Token exchange failed")
