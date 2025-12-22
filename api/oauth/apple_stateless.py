import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt, JWTError
import requests

from api.oauth.config import get_auth_config
from api.oauth.base_oauth import OAuthProvider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/apple", tags=["auth-apple"])

# Initialize the OAuth provider
_OAUTH_PROVIDER = OAuthProvider(
    provider_name="Apple",
    state_cookie_name="a_oidc_state",
    state_secret=os.getenv("APPLE_STATE_SECRET_KEY", os.getenv("STATE_SECRET_KEY", "change-me-state-secret")),
    state_ttl_seconds=600
)


def _normalize_platform(value: str | None) -> str:
    """Normalize platform name to lowercase, defaulting to 'web'."""
    return (value or "web").lower()


def get_platform_client_config(platform: str, include_secrets: bool = False) -> Dict[str, Any]:
    """
    Get Apple OAuth configuration for the specified platform.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        include_secrets: Whether to include sensitive information like key_id and auth_key_path
        
    Returns:
        dict: Configuration containing Apple OAuth parameters
        
    Raises:
        HTTPException: If configuration is not found or invalid
    """
    try:
        cfg = get_auth_config("apple", platform)
        config = {
            "platform": platform,
            "client_id": cfg.client_id,
            "authorization_endpoint": cfg.authorization_endpoint,
            "token_endpoint": cfg.token_endpoint,
        }
        
        # Only include sensitive information for internal server calls
        if include_secrets:
            config.update({
                "team_id": cfg.team_id,
                "key_id": cfg.key_id,
                "auth_key_path": cfg.auth_key_path,
            })
            
        return config
    except Exception as e:
        logger.error("Failed to load Apple config for platform '%s': %s", platform, e)
        raise HTTPException(
            status_code=500,
            detail=f"Apple authentication is not properly configured for platform '{platform}'"
        ) from e


def _get_internal_config(platform: str) -> Dict[str, Any]:
    """
    Get Apple OAuth configuration including sensitive information for internal use only.
    This should only be used by server-side components that need the private key.
    """
    return get_platform_client_config(platform, include_secrets=True)


@router.get("/config")
async def get_client_config(platform: str):
    """
    Get Apple OAuth configuration for the specified platform.
    This endpoint is safe to expose to clients as it doesn't return sensitive information.
    
    Args:
        platform: The target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        JSON: Configuration containing Apple OAuth parameters (without sensitive data)
    """
    platform = _normalize_platform(platform)
    return get_platform_client_config(platform, include_secrets=False)


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
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to load Apple private key: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to load Apple authentication key. Please check the configuration."
        ) from e


def _build_apple_client_secret(client_cfg) -> str:
    """Build Apple client secret JWT using ES256 and your .p8 key."""
    if not (client_cfg.get("client_id") and client_cfg.get("team_id") and 
            client_cfg.get("key_id") and client_cfg.get("auth_key_path")):
        raise RuntimeError("Apple config incomplete (client_id/team_id/key_id/auth_key_path)")

    import time
    now = int(time.time())
    claims = {
        "iss": client_cfg["team_id"],
        "iat": now,
        "exp": now + 1800,
        "aud": "https://appleid.apple.com",
        "sub": client_cfg["client_id"],
    }
    headers = {"kid": client_cfg["key_id"]}
    private_key = _load_apple_private_key(client_cfg["auth_key_path"])
    return jwt.encode(claims, private_key, algorithm="ES256", headers=headers)


def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    client_cfg: Dict[str, Any],
    code_verifier: Optional[str] = None,
) -> Dict[str, Any]:
    token_endpoint = client_cfg.get("token_endpoint")
    if not token_endpoint:
        raise RuntimeError("APPLE_TOKEN_ENDPOINT must be configured")

    client_secret = _build_apple_client_secret(client_cfg)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_cfg["client_id"],
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail="Apple token endpoint error"
        )

    logger.info("Apple OIDC token response: %s", payload)
    return payload


@router.post("/state")
async def issue_state_post(request: Request):
    body = await request.json()
    platform = _normalize_platform(body.get("platform"))
    code_verifier = body.get("code_verifier")
    if not platform:
        raise HTTPException(status_code=400, detail="Missing required parameter: platform")

    get_platform_client_config(platform)

    extra_state_data = {}
    if code_verifier:
        extra_state_data["code_verifier"] = code_verifier

    state_data = _OAUTH_PROVIDER.create_state_response(request, platform, extra_state_data=extra_state_data)
    resp = JSONResponse({
        "state": state_data["state"],
        "platform": state_data["platform"],
    })

    resp.set_cookie(
        key=_OAUTH_PROVIDER.state_cookie_name,
        value=state_data["signed_state"],
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


async def _exchange_callback(code: str, redirect_uri: str, config: Dict[str, Any], code_verifier: Optional[str]) -> Dict[str, Any]:
    """Exchange authorization code for tokens."""
    return _exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        client_cfg=config,
        code_verifier=code_verifier,
    )


@router.get("/callback")
async def callback(request: Request):
    """Handle OAuth callback from Apple."""
    return await _OAUTH_PROVIDER.handle_callback(
        request=request,
        exchange_callback=_exchange_callback,
        success_html_title="Apple Login Complete",
        success_html_heading="Apple authentication completed",
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
            client_cfg=config,
            code_verifier=code_verifier
        )
        return tokens
    except Exception as e:
        logger.error("Token exchange failed: %s", str(e))
        raise HTTPException(status_code=400, detail="Token exchange failed")
