"""
Base OAuth implementation that can be used by multiple providers.
"""
import logging
import secrets
import time
from typing import Any, Callable, Dict, Optional, Tuple
import os
import json
from datetime import datetime, timezone
from urllib.parse import quote as Uri
from api.oauth import jwt_utils
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
        token_generator_func: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
        storage_func: Optional[Callable[[Dict[str, Any], str, str], None]] = None,
        user_info_func: Optional[Callable[[Dict[str, Any], str, str], Dict[str, Any]]] = None,
        cookie_generator_func: Optional[Callable[[str, str, str], Dict[str, Any]]] = None,
    ):
        self.provider_name = provider_name
        self.state_cookie_name = state_cookie_name
        self.state_secret = state_secret
        self.state_ttl_seconds = state_ttl_seconds
        self.state_alg = "HS256"
        self.token_generator_func = token_generator_func
        self.storage_func = storage_func
        self.client_user_info_func = user_info_func
        self.cookie_generator_func = cookie_generator_func
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
        
        # Add extra state data if provided - this includes return_url and other parameters
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
    
    async def _extract_oauth_params_and_verify_state(
        self, 
        request: Request
    ) -> Tuple[str, str, str, Optional[str]]:
        """Extract OAuth parameters and verify state token.
        
        Args:
            request: The incoming request
            
        Returns:
            Tuple containing: (code, state, platform, code_verifier)
            
        Raises:
            HTTPException: If parameters are missing or state verification fails
        """
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
        
        return code, state, platform, code_verifier

    def _get_deep_link_scheme(self, config) -> str:
        """Get deep link scheme from config with default fallback.
        
        Args:
            config: The OAuth configuration (dict or object)
            
        Returns:
            str: Deep link scheme (defaults to "voiceassistance")
        """
        deep_link_scheme = "voiceassistance"
        if isinstance(config, dict) and config.get("deep_link_scheme"):
            deep_link_scheme = config["deep_link_scheme"]
        elif hasattr(config, 'deep_link_scheme') and config.deep_link_scheme:
            deep_link_scheme = config.deep_link_scheme
        return deep_link_scheme

    def _create_auth_response(
        self,
        request: Request,
        platform: str,
        token: str,
        user_client_info: Dict[str, Any],
        return_url: str,
        json_data: Dict[str, Any],
        config: Any,
        is_success: bool = True,
        error_message: Optional[str] = None,
        status_code: int = 200,
        should_redirect: bool = True
    ) -> HTMLResponse | JSONResponse:
        """Create authentication response (success or error).
        
        Args:
            request: The incoming request
            platform: The platform (web, ios, android)
            token: JWT token (empty string for errors)
            user_client_info: Client information dictionary
            return_url: URL to return to
            json_data: JSON data for the response
            config: OAuth configuration
            is_success: Whether this is a success response
            error_message: Error message (for error responses)
            status_code: HTTP status code
            should_redirect: Whether to redirect (True) or return JSON (False)
            
        Returns:
            HTMLResponse | JSONResponse: The appropriate response
        """
        # If should_redirect is True, redirect to app with result
        # Otherwise, return JSON response
        if should_redirect:
            if is_success:
                # Create deep link URL with essential result only
                deep_link_url = f"{self._get_deep_link_scheme(config)}://auth/callback?success=true&token={token}"
                
                # Add essential client info
                if user_client_info.get("va-dir"):
                    deep_link_url += f"&va-dir={Uri(user_client_info['va-dir'])}"
                if user_client_info.get("Name"):
                    deep_link_url += f"&name={Uri(user_client_info['Name'])}"
            else:
                # Create deep link URL with error information
                deep_link_url = f"{self._get_deep_link_scheme(config)}://auth/callback?success=false&error={Uri(error_message)}"
                
                # Add provider info if available
                provider_name = getattr(self, 'provider_name', 'unknown')
                if provider_name != 'unknown':
                    deep_link_url += f"&provider={provider_name}"
            
            response = RedirectResponse(url=deep_link_url, status_code=302)
        else:
            # Return JSON response for non-web platforms or HTML for web platforms
            if platform.lower() != "web":
                # Return JSON response for native flows
                response = JSONResponse(
                    content=json_data,
                    status_code=status_code if not is_success else 200
                )
            else:
                # Return HTML response for web platform
                if is_success:
                    template_data = {
                        "request": request,
                        "success_html_title": user_client_info.get("success_html_title", "Authentication successful"),
                        "success_html_heading": user_client_info.get("success_html_heading", "Authentication successful"),
                        "token": token,
                        "is_success": True,
                        "va-dir": user_client_info.get("va-dir", ""),
                        "Name" : user_client_info.get("Name", ""),
                        "return_url": return_url,
                        "json_data": json.dumps(json_data)
                    }
                else:
                    template_data = {
                        "request": request,
                        "success_html_title": "Authentication failed",
                        "success_html_heading": "Authentication failed",
                        "token": "",
                        "is_success": False,
                        "error_message": error_message,
                        "return_url": return_url,
                        "json_data": json.dumps(json_data)
                    }
                
                response = self.templates.TemplateResponse(
                    "auth_result.html",
                    template_data,
                    status_code=status_code if not is_success else 200,
                )
        
        # Set the JWT token in an HTTP-only cookie using the cookie generator function
        if token and self.cookie_generator_func:
            cookie_config = self.cookie_generator_func(token, platform, self.provider_name)
            response.set_cookie(**cookie_config)
        elif token:
            # Default cookie setting for backward compatibility
            jwt_expire_hours = int(os.getenv('JWT_EXPIRE_HOURS', '24'))
            response.set_cookie(
                key="auth_token",
                value=token,
                httponly=True,
                secure=True,  # Only send over HTTPS in production
                samesite='lax',  # Helps prevent CSRF attacks
                max_age=jwt_expire_hours * 3600,  # Match JWT expiration
                domain=None,  # Let browser use default (current domain)
                path='/',  # Make cookie available across the entire site
            )
        
        return response

    async def handle_callback(
        self,
        request: Request,
        exchange_callback: Callable[..., Any],
        success_html_title: str,
        success_html_heading: str,
        config_loader: Callable[[str], Any],
        user_info_extractor: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        # Parameter extraction function that handles both extraction and state verification
        param_extractor: Optional[Callable[[Request], Tuple[str, Optional[str], str, Optional[str], str]]] = None,
        should_redirect: bool = False
    ) -> HTMLResponse | JSONResponse:
        """Handle OAuth callback.
        
        Args:
            request: The incoming request
            exchange_callback: Function to exchange code for tokens
            success_html_title: Title for success page
            success_html_heading: Heading for success page
            config_loader: Function to load provider config
            user_info_extractor: Function to extract user info from OAuth result
            param_extractor: Function that extracts parameters and optionally verifies state.
                           Returns: (code, state, platform, code_verifier, return_url)
                           If None, uses default server-mediated OAuth extraction.
            should_redirect: Whether to redirect response (True) or return JSON/HTML (False)
            
        Returns:
            HTMLResponse | JSONResponse: The response to return to the client
        """
        logger.info("Handling OAuth callback request")
        response: Optional[HTMLResponse | JSONResponse] = None
        try:
            # Use custom parameter extractor or default server-mediated extraction
            if param_extractor:
                # Custom parameter extraction (e.g., for native flows)
                code, state, platform, code_verifier, return_url = await param_extractor(request)
                # For native flows, return_url comes from the extractor and defaults to None
                # We won't do redirection for native flows - just return JSON response
            else:
                # Default server-mediated OAuth parameter extraction and state verification
                code, state, platform, code_verifier = await self._extract_oauth_params_and_verify_state(request)
                if not code:
                    raise HTTPException(status_code=400, detail="No authorization code provided")
                logger.debug(f"Extracted OAuth params - code: {bool(code)}, state: {bool(state)}, platform: {platform}")
                
                # Extract return_url from state payload
                state_cookie_value = request.cookies.get(self.state_cookie_name)
                state_payload = self._verify_state_and_get_payload(state_cookie_value, state)
                return_url = state_payload.get("return_url", "/")
            
            # Load provider config
            config = config_loader(platform)
            logger.debug(f"Loaded config for platform: {platform}")

            # Process the authorization code
            redirect_uri = str(request.url.replace(query=""))
            logger.info("Exchanging authorization code for tokens")
            logger.debug(f"Using redirect_uri: {redirect_uri}")
            logger.debug(f"Using code_verifier: {bool(code_verifier)}")
            logger.debug(f"Using platform: {platform}")
            logger.debug(f"Using config: {config.get('client_id') if config else 'N/A'}")
            result = await exchange_callback(code, redirect_uri, config, code_verifier)
            
            # Log successful token exchange
            logger.info("Successfully exchanged authorization code for tokens")
            if isinstance(result, dict):
                log_result = {k: v for k, v in result.items() 
                            if k not in ['access_token', 'refresh_token', 'id_token']}
                logger.debug("Token exchange result: %s", log_result)

            # Extract user info using the provider-specific extractor function
            try:
                user_info = user_info_extractor(result, config) if isinstance(result, dict) else {}
                logger.debug("User info extracted: %s", user_info)
                logger.debug("User ID: %s, Email: %s, Name: %s", 
                            user_info.get('id'), user_info.get('email'), user_info.get('name'))
            except Exception as e:
                logger.error("Failed to extract user info: %s", str(e), exc_info=True)
                user_info = {}
            
            # Generate JWT token using the injected function
            if self.token_generator_func:
                token = self.token_generator_func(user_info, platform, self.provider_name)
            else:
                token = jwt_utils.generate_jwt_token(user_info, platform, self.provider_name)

            # Use the configured callback functions
            if self.storage_func:
                self.storage_func(user_info, platform, self.provider_name)
            
            if self.client_user_info_func:
                user_client_info = self.client_user_info_func(user_info, platform, self.provider_name)
            else:
                # No user info function configured - use minimal client info
                user_client_info = {
                    "success_html_title": "Authentication successful",
                    "success_html_heading": "Authentication successful",
                    "va-dir": "",
                    "Name": ""
                }

            
            # Prepare JSON data for response
            json_data = {
                "user_info": user_client_info,
                "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "provider": getattr(self, 'provider_name', 'unknown'),
                "token": token
            }
            
            response = self._create_auth_response(
                request=request,
                platform=platform,
                token=token,
                user_client_info=user_client_info,
                return_url=return_url,
                json_data=json_data,
                config=config,
                is_success=True,
                should_redirect=should_redirect
            )
            
            return response

        except HTTPException as he:
            msg = str(he.detail)
            
            # Extract return_url from state payload for error case
            state_cookie_value = request.cookies.get(self.state_cookie_name)
            return_url = "/"
            if state_cookie_value:
                try:
                    state_payload = self._decode_state_cookie(state_cookie_value)
                    return_url = state_payload.get("return_url", "/")
                except Exception:
                    logger.debug("Could not extract return_url from state cookie in error case")
            
            # Prepare JSON data for error response
            json_data = {
                "error": msg,
                "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "provider": getattr(self, 'provider_name', 'unknown')
            }
            
            response = self._create_auth_response(
                request=request,
                platform=platform,
                token="",
                user_client_info={},
                return_url=return_url,
                json_data=json_data,
                config=config,
                is_success=False,
                error_message=msg,
                status_code=he.status_code,
                should_redirect=should_redirect
            )
            
            return response

        except Exception as e:
            logger.critical("Unhandled exception in OAuth callback: %s", str(e), exc_info=True)
            msg = "An unexpected error occurred during authentication"
            
            # Extract return_url from state payload for error case
            state_cookie_value = request.cookies.get(self.state_cookie_name)
            return_url = "/"
            if state_cookie_value:
                try:
                    state_payload = self._decode_state_cookie(state_cookie_value)
                    return_url = state_payload.get("return_url", "/")
                except Exception:
                    logger.debug("Could not extract return_url from state cookie in error case")
            
            # Prepare JSON data for error response
            json_data = {
                "error": msg,
                "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "provider": getattr(self, 'provider_name', 'unknown')
            }
            
            response = self._create_auth_response(
                request=request,
                platform=platform,
                token="",
                user_client_info={},
                return_url=return_url,
                json_data=json_data,
                config=config,
                is_success=False,
                error_message=msg,
                status_code=500,
                should_redirect=should_redirect
            )
            
            return response

        finally:
            if response is not None:
                response.delete_cookie(key=self.state_cookie_name, path="/")
