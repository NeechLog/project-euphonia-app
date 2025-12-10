"""
Base OAuth implementation that can be used by multiple providers.
"""
import logging
import secrets
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

class OAuthProvider:
    """Base class for OAuth providers."""
    
    def __init__(
        self,
        provider_name: str,
        state_cookie_name: str,
        state_secret: str,
        state_ttl_seconds: int = 600,
    ):
        self.provider_name = provider_name
        self.state_cookie_name = state_cookie_name
        self.state_secret = state_secret
        self.state_ttl_seconds = state_ttl_seconds
        self.state_alg = "HS256"
    
    def _normalize_platform(self, platform: Optional[str]) -> str:
        """Normalize platform name to lowercase, defaulting to 'web'."""
        return (platform or "web").lower()
    
    def _encode_state_cookie(self, state: str, platform: str) -> str:
        """Encode state into a JWT cookie."""
        now = int(time.time())
        payload = {
            "state": state,
            "platform": platform,
            "iat": now,
            "exp": now + self.state_ttl_seconds,
        }
        return jwt.encode(payload, self.state_secret, algorithm=self.state_alg)
    
    def _decode_state_cookie(self, token: str) -> Dict[str, Any]:
        """Decode state from a JWT cookie."""
        return jwt.decode(token, self.state_secret, algorithms=[self.state_alg])
    
    def create_state_response(
        self,
        request: Request,
        platform: str,
        extra_state_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Create a new state token and return it in a response."""
        platform = self._normalize_platform(platform)
        state = secrets.token_urlsafe(32)
        
        # Add extra state data if provided
        state_data = {"state": state, "platform": platform}
        if extra_state_data:
            state_data.update(extra_state_data)
            
        signed = jwt.encode(
            state_data,
            self.state_secret,
            algorithm=self.state_alg
        )
        
        return {
            "state": state,
            "platform": platform,
            "signed_state": signed
        }
    
    async def handle_callback(
        self,
        request: Request,
        exchange_callback: Callable[[str, str, Any], Any],
        success_html_title: str,
        success_html_heading: str,
        config_loader: Callable[[str], Any]
    ) -> HTMLResponse:
        """Handle OAuth callback.
        
        Args:
            request: The incoming request
            exchange_callback: Function to exchange code for tokens
            success_html_title: Title for success page
            success_html_heading: Heading for success page
            config_loader: Function to load provider config
            
        Returns:
            HTMLResponse: The response to return to the client
        """
        params = dict(request.query_params)
        code = params.get("code")
        state = params.get("state")

        if not state:
            raise HTTPException(status_code=400, detail="Missing state in callback")

        cookie = request.cookies.get(self.state_cookie_name)
        if not cookie:
            raise HTTPException(status_code=400, detail="Missing state cookie")

        try:
            state_payload = self._decode_state_cookie(cookie)
        except JWTError as exc:
            logger.warning("Invalid state cookie: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid state cookie") from exc

        expected_state = state_payload.get("state")
        platform = state_payload.get("platform", "web")

        if not expected_state or expected_state != state:
            logger.warning(
                "%s state mismatch: expected %s, got %s",
                self.provider_name, expected_state, state
            )
            raise HTTPException(status_code=400, detail="State mismatch")

        config = config_loader(platform)
        logger.info(
            "%s OIDC callback received. code=%s, state=%s",
            self.provider_name, code, state
        )

        if code:
            try:
                redirect_uri = str(request.url.replace(query=""))
                exchange_callback(code, redirect_uri, config)
            except Exception as exc:
                logger.error(
                    "%s server-side code exchange failed: %s",
                    self.provider_name, exc, exc_info=True
                )

        html = f"""<!DOCTYPE html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>{success_html_title}</title></head>
  <body style=\"font-family: sans-serif; text-align: center; margin-top: 3rem;\">
    <h1>{success_html_heading}</h1>
    <p>You may now return to the application.</p>
  </body>
</html>"""
        return HTMLResponse(content=html)
