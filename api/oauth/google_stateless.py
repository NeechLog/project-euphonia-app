import os
import time
import secrets
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests
from google.auth import jwt as google_jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from api.oauth.config import get_auth_config, init_auth_config
from api.oauth.base_oauth import OAuthProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth-google"])

# OAuth provider instance will be created on demand with token generator function
_OAUTH_PROVIDER: Optional[OAuthProvider] = None

def get_oauth_provider() -> OAuthProvider:
    """Get OAuth provider instance with token generator function from config."""
    global _OAUTH_PROVIDER
    if _OAUTH_PROVIDER is None:
        # Try to get token generator from auth config
        try:
            from api.oauth.config import _auth_config
            token_generator_func = _auth_config.get_token_generator_func() if _auth_config else None
        except (ImportError, AttributeError):
            token_generator_func = None
        
        _OAUTH_PROVIDER = OAuthProvider(
            provider_name="Google",
            state_cookie_name="g_oidc_state",
            state_secret=os.getenv("GOOGLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret")),
            state_ttl_seconds=600,
            token_generator_func=token_generator_func
        )
    return _OAUTH_PROVIDER


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
            "userinfo_endpoint": getattr(cfg, 'userinfo_endpoint', 'https://www.googleapis.com/oauth2/v2/userinfo'),
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
        
@router.post("/state")
async def issue_state_post(request: Request):
    logger.info("State token requested (POST)")
    body = await request.json()
    platform = body.get("platform")
    code_verifier = body.get("code_verifier")
    if not platform:
        raise HTTPException(status_code=400, detail="Missing required parameter: platform")

    platform = _normalize_platform(platform)
    get_platform_config(platform)

    extra_state_data = {}
    if code_verifier:
        extra_state_data["code_verifier"] = code_verifier

    state_data = get_oauth_provider().create_state_response(request, platform, extra_state_data=extra_state_data)

    response = JSONResponse(content={
        "state": state_data["state"],
        "platform": state_data["platform"],
    })

    response.set_cookie(
        key=get_oauth_provider().state_cookie_name,
        value=state_data["signed_state"],
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


def _extract_user_info_from_id_token(id_token_str: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user information from Google ID token using google-auth library.
    
    Args:
        id_token_str: The ID token string from Google OAuth result
        config: Google OAuth configuration containing client_id for audience verification
        
    Returns:
        Dict[str, Any]: Extracted user information or empty dict if failed
    """
    try:
        # Verify and decode the ID token with proper audience verification
        request = google_requests.Request()
        client_id = config.get('client_id')
        id_info = id_token.verify_oauth2_token(
            id_token_str, 
            request, 
            client_id  # Use client_id for proper audience verification
        )
        
        # Extract standard fields from Google ID token
        user_info = {
            'id': id_info.get('sub'),
            'email': id_info.get('email'),
            'name': id_info.get('name'),
            'given_name': id_info.get('given_name'),
            'family_name': id_info.get('family_name'),
            'picture': id_info.get('picture'),
            'locale': id_info.get('locale'),
            'email_verified': id_info.get('email_verified', False),
            'provider': 'google'
        }
        
        logger.debug("Successfully extracted user info from ID token: %s", 
                   {k: v for k, v in user_info.items() if k != 'picture'})
        return user_info
        
    except Exception as e:
        logger.warning("Failed to verify Google ID token: %s", str(e))
        return {}


def _extract_user_info_from_endpoint(access_token: str, userinfo_endpoint: str) -> Dict[str, Any]:
    """
    Extract user information from Google's userinfo endpoint using access token.
    
    Args:
        access_token: The OAuth access token
        userinfo_endpoint: The userinfo endpoint URL from config
        
    Returns:
        Dict[str, Any]: Extracted user information or empty dict if failed
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(userinfo_endpoint, headers=headers, timeout=10)
        
        if response.ok:
            google_user_info = response.json()
            
            user_info = {
                'id': google_user_info.get('id'),
                'email': google_user_info.get('email'),
                'name': google_user_info.get('name'),
                'given_name': google_user_info.get('given_name'),
                'family_name': google_user_info.get('family_name'),
                'picture': google_user_info.get('picture'),
                'locale': google_user_info.get('locale'),
                'verified_email': google_user_info.get('verified_email', False),
                'provider': 'google'
            }
            
            logger.debug("Successfully extracted user info from userinfo endpoint: %s", 
                       {k: v for k, v in user_info.items() if k != 'picture'})
            return user_info
        else:
            logger.warning("Userinfo endpoint returned status %d: %s", 
                         response.status_code, response.text)
            
    except Exception as e:
        logger.warning("Failed to get user info from Google userinfo endpoint: %s", str(e))
    
    return {}


def _extract_google_user_info(oauth_result: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user information from Google OAuth result using google-auth library.
    
    Args:
        oauth_result: The OAuth result from Google containing tokens and potentially user info
        config: Google OAuth configuration containing endpoints
        
    Returns:
        Dict[str, Any]: Extracted user information with standardized fields
    """
    logger.debug("Extracting Google user info from OAuth result")
    
    try:
        # First try to get user info from id_token if present
        id_token_str = oauth_result.get('id_token')
        if id_token_str:
            user_info = _extract_user_info_from_id_token(id_token_str, config)
            if user_info:
                return user_info
        
        # If ID token extraction fails, try to use access_token to get user info
        access_token = oauth_result.get('access_token')
        if access_token:
            userinfo_endpoint = config.get('userinfo_endpoint', 'https://www.googleapis.com/oauth2/v2/userinfo')
            user_info = _extract_user_info_from_endpoint(access_token, userinfo_endpoint)
            if user_info:
                return user_info
        
        # If both methods fail, return empty dict
        logger.warning("Could not extract user info from Google OAuth result")
        return {}
        
    except Exception as e:
        logger.error("Unexpected error extracting Google user info: %s", str(e), exc_info=True)
        return {}


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
    async def exchange_callback(code: str, redirect_uri: str, config: Dict[str, Any], code_verifier: str | None) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        return _exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            client_config=config,
            code_verifier=code_verifier,
        )
    
    return await get_oauth_provider().handle_callback(
        request=request,
        exchange_callback=exchange_callback,
        success_html_title="Google Login Complete",
        success_html_heading="Google authentication completed",
        config_loader=_get_internal_config,
        user_info_extractor=_extract_google_user_info
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
