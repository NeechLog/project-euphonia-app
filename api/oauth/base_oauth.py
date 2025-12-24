"""
Base OAuth implementation that can be used by multiple providers.
"""
import logging
import secrets
import time
from typing import Any, Callable, Dict, Optional, Tuple
import os
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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
        self.templates = Jinja2Templates(directory="web/auth")
    
    def _normalize_platform(self, platform: Optional[str]) -> str:
        """Normalize platform name to lowercase, defaulting to 'web'."""
        normalized = (platform or "web").lower()
        logger.debug("Normalized platform from '%s' to '%s'", platform, normalized)
        return normalized
    
    def _encode_state_cookie(self, state: str, platform: str, extra_state_data: Optional[Dict[str, Any]] = None) -> str:
        """Encode state into a JWT cookie."""
        now = int(time.time())
        payload = {
            "state": state,
            "platform": platform,
            "iat": now,
            "exp": now + self.state_ttl_seconds,
        }
        if extra_state_data:
            payload.update(extra_state_data)
        logger.debug("Encoding state cookie for platform: %s, expires in: %d seconds", 
                    platform, self.state_ttl_seconds)
        try:
            token = jwt.encode(payload, self.state_secret, algorithm=self.state_alg)
            logger.debug("Successfully encoded state token")
            return token
        except Exception as e:
            logger.error("Failed to encode state token: %s", str(e), exc_info=True)
            raise
    
    def _decode_state_cookie(self, token: str) -> Dict[str, Any]:
        """Decode state from a JWT cookie."""
        logger.debug("Decoding state token")
        try:
            payload = jwt.decode(token, self.state_secret, algorithms=[self.state_alg])
            logger.debug("Successfully decoded state token for platform: %s", 
                        payload.get('platform', 'unknown'))
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Expired state token received")
            raise HTTPException(status_code=400, detail="State token has expired")
        except JWTError as e:
            logger.error("Invalid state token: %s", str(e), exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid state token")
        except Exception as e:
            logger.error("Error decoding state token: %s", str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Error processing state token")
    
    def _verify_state_and_get_payload(self, cookeie_state_value: str, state: str) -> Dict[str, Any]:
        """Verify the state token from the request and return the decoded payload."""
        try:
            logger.debug("Verifying state token")
            payload = self._decode_state_cookie(cookeie_state_value)
            logger.debug("State token verified for state: %s", payload.get('state', 'unknown'))
            if payload.get("state") != state:
                raise HTTPException(status_code=400, detail="Invalid state parameter")
            return payload
        except Exception as e:
            logger.error("State verification failed: %s", str(e), exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid state parameter")

    def _verify_state_and_get_platform(self, cookeie_state_value: str, state: str) -> str:
        """Verify the state token from the request and return the platform.
        
        Args:
            request: The request object containing the state cookie
            state: The state parameter from the OAuth callback
            
        Returns:
            str: The platform extracted from the state token
            
        Raises:
            HTTPException: If state verification fails
        """
        payload = self._verify_state_and_get_payload(cookeie_state_value, state)
        return payload.get("platform", "unknown")
    
    def create_state_response(
        self,
        request: Request,
        platform: str,
        extra_state_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Create a new state token and return it in a response."""
        logger.info("Creating new state response for platform: %s", platform)
        platform = self._normalize_platform(platform)
        ## DO NOT DELETE THIS COMMENT TILL WE FIGURE THIS OUT.
        ##  TODO: set up some kind of set of states that are valid for a given platform and given client detaisl inside the request. 
        ##       This will help prevent replay attacks. Question - should we have full request here or just 
        ##       some kind of hash of the request or just some kind of random string?
        
        state = secrets.token_urlsafe(32)
        
        # Add extra state data if provided
        state_data = {"state": state, "platform": platform}
        if extra_state_data:
            logger.debug("Adding extra state data: %s", extra_state_data)
            state_data.update(extra_state_data)
            
        try:
            signed = self._encode_state_cookie(state, platform, extra_state_data=extra_state_data)
            logger.debug("Successfully created signed state")
            
            response_data = {
                "state": state,
                "platform": platform,
                "signed_state": signed
            }
            
            logger.info("Successfully created state response for platform: %s", platform)
            return response_data
            
        except Exception as e:
            logger.error("Failed to create state response: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to create authentication state"
            )
    
    async def handle_callback(
        self,
        request: Request,
        exchange_callback: Callable[..., Any],
        success_html_title: str,
        success_html_heading: str,
        config_loader: Callable[[str], Any],
        user_info_extractor: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    ) -> HTMLResponse:
        """Handle OAuth callback.
        
        Args:
            request: The incoming request
            exchange_callback: Function to exchange code for tokens
            success_html_title: Title for success page
            success_html_heading: Heading for success page
            config_loader: Function to load provider config
            user_info_extractor: Function to extract user info from OAuth result
            
        Returns:
            HTMLResponse: The response to return to the client
        """
        logger.info("Handling OAuth callback request")

        response: Optional[HTMLResponse] = None
        try:
            # Log basic request info
            client_host = request.client.host if request.client else "unknown"
            logger.debug("OAuth callback from %s with query params: %s", 
                        client_host, dict(request.query_params))
            
            params = dict(request.query_params)
            if request.method.upper() == "POST":
                try:
                    form = await request.form()
                    params.update(dict(form))
                except Exception:
                    pass
            code = params.get("code")
            state = params.get("state")
            
            logger.debug("Received OAuth callback - code present: %s, state present: %s", 
                        bool(code), bool(state))

            if not code or not state:
                error_msg = "Missing required parameters: code and state are required"
                logger.warning("Invalid OAuth callback: %s", error_msg)
                raise HTTPException(
                    status_code=400,
                    detail=error_msg
                )

            # Verify state token
            state_cookie_value = request.cookies.get(self.state_cookie_name)
            if not state_cookie_value:
                raise HTTPException(status_code=400, detail="Missing state cookie")
            state_payload = self._verify_state_and_get_payload(state_cookie_value, state)
            platform = state_payload.get("platform", "unknown")
            code_verifier = state_payload.get("code_verifier")
            if not platform:
                raise HTTPException(status_code=400, detail="Mismatch state parameter")
            logger.debug("State verified for platform: %s", platform)

            # Load provider config
            try:
                logger.debug("Loading provider config for platform: %s", platform)
                config = config_loader(platform)
                logger.debug("Successfully loaded config for platform: %s", platform)
            except Exception as e:
                logger.error("Failed to load config for platform %s: %s", 
                            platform, str(e), exc_info=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid platform: {platform}"
                )

            # Process the authorization code
            if code:
                try:
                    logger.info("Exchanging authorization code for tokens")
                    redirect_uri = str(request.url.replace(query=""))
                    result = await exchange_callback(code, redirect_uri, config, code_verifier)
                    
                    # Log successful token exchange (without sensitive data)
                    if isinstance(result, dict):
                        log_result = {k: v for k, v in result.items() 
                                    if k not in ['access_token', 'refresh_token', 'id_token']}
                        logger.info("Successfully exchanged code for tokens. Result: %s", log_result)
                    else:
                        logger.info("Successfully exchanged code for tokens")
                    
                except HTTPException as he:
                    logger.error("HTTP error during token exchange: %s (status_code=%d)", 
                                str(he.detail), he.status_code, exc_info=True)
                    raise
                except Exception as e:
                    logger.error("Unexpected error during token exchange: %s", 
                                str(e), exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail="An error occurred during token exchange"
                    )

            # Extract user info using the provider-specific extractor function
            try:
                user_info = user_info_extractor(result, config) if isinstance(result, dict) else {}
                logger.debug("User info extracted: %s", user_info)
                logger.debug("User ID: %s, Email: %s, Name: %s", 
                            user_info.get('id'), user_info.get('email'), user_info.get('name'))
            except Exception as e:
                logger.error("Failed to extract user info: %s", str(e), exc_info=True)
                user_info = {}
            
            # Generate JWT token using the utility function
            from .jwt_utils import generate_jwt_token
            token = generate_jwt_token(user_info, platform)
            
            # Return success response with token in a secure HTTP-only cookie
            response = self.templates.TemplateResponse(
                "auth_result.html",
                {
                    "request": request,
                    "success_html_title": success_html_title,
                    "success_html_heading": success_html_heading,
                    "token": token
                }
            )
            
            # Set the JWT token in an HTTP-only cookie for additional security
            jwt_expire_hours = int(os.getenv('JWT_EXPIRE_HOURS', '24'))
            response.set_cookie(
                key="auth_token",
                value=token,
                httponly=True,
                secure=os.getenv('ENVIRONMENT') == 'production',  # Only send over HTTPS in production
                samesite='lax',  # Helps prevent CSRF attacks
                max_age=jwt_expire_hours * 3600  # Match JWT expiration
            )
            
            return response

        except HTTPException as he:
            msg = str(he.detail)
            response = self.templates.TemplateResponse(
                "auth_result.html",
                {
                    "request": request,
                    "success_html_title": "Authentication failed",
                    "success_html_heading": "Authentication failed",
                    "token": "",
                    "is_success": False,
                    "error_message": msg,
                },
                status_code=he.status_code,
            )
            return response

        except Exception as e:
            logger.critical("Unhandled exception in OAuth callback: %s", str(e), exc_info=True)
            msg = "An unexpected error occurred during authentication"
            response = self.templates.TemplateResponse(
                "auth_result.html",
                {
                    "request": request,
                    "success_html_title": "Authentication failed",
                    "success_html_heading": "Authentication failed",
                    "token": "",
                    "is_success": False,
                    "error_message": msg,
                },
                status_code=500,
            )
            return response

        finally:
            if response is not None:
                response.delete_cookie(key=self.state_cookie_name, path="/")
