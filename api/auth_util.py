"""Authentication utilities for token generation and validation."""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from fastapi import Cookie, HTTPException, status, Depends, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt

# Cookie constants
AUTH_COOKIE_KEY = "auth_token"

# JWT constants
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '24'))

# Logger
logger = logging.getLogger(__name__)

# Create auth router for user endpoints
auth_router = APIRouter(prefix="/user", tags=["user"])

@auth_router.get('/current')
async def get_current_user_info(auth_context: dict = Depends(get_auth_context)):
    """
    Endpoint to retrieve current user information from authentication context.
    
    Returns:
        JSON response containing user name and va-dir
        Example: {"Name": "John Doe", "va-dir": "google_12345"}
    """
    try:
        if not auth_context['authenticated']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not authenticated"
            )
        
        user_info = {
            "authenticated": auth_context['authenticated'],
            "Name": auth_context['name']    ,
            "va-dir": auth_context['va_dir'],
            "auth_source": auth_context['auth_source']
        }
        
        logger.info(f"Retrieving user info: {user_info}")
        return user_info
    except Exception as e:
        error_msg = f"Error retrieving user info: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

def generate_auth_cookies(token: str, platform: str, provider_name: str) -> Dict[str, Any]:
    """
    Generate authentication cookie configuration for setting secure HTTP-only cookies.
    
    Args:
        token: JWT token string to set in the cookie
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        provider_name: The OAuth provider name (e.g., 'google', 'apple')
        
    Returns:
        Dict[str, Any]: Cookie configuration dictionary with settings for secure cookies
    """
    try:
        # Get JWT expiration from environment or use default
        jwt_expire_hours = int(os.getenv('JWT_EXPIRE_HOURS', '24'))
        
        # Build cookie configuration
        cookie_config = {
            "key": AUTH_COOKIE_KEY,
            "value": token,
            "httponly": True,
            "secure": True,  # Only send over HTTPS in production
            "samesite": 'lax',  # Helps prevent CSRF attacks
            "max_age": jwt_expire_hours * 3600,  # Match JWT expiration
            "domain": None,  # Let browser use default (current domain)
            "path": '/',  # Make cookie available across the entire site
        }
        
        logger.debug(f"Generated cookie config for {provider_name} on {platform}")
        return cookie_config
        
    except Exception as e:
        logger.error(f"Error in generate_auth_cookies: {e}", exc_info=True)
        # Return fallback basic cookie config
        return {
            "key": AUTH_COOKIE_KEY,
            "value": token,
            "httponly": True,
            "secure": True,
            "samesite": 'lax',
            "max_age": 24 * 3600,  # 24 hours default
            "domain": None,
            "path": '/',
        }

def delete_auth_cookies() -> Dict[str, Any]:
    """
    Generate cookie configuration to delete the authentication cookie.
    
    Returns:
        Dict[str, Any]: Cookie configuration dictionary with settings to delete the cookie
    """
    try:
        # Build cookie deletion configuration
        cookie_config = {
            "key": AUTH_COOKIE_KEY,
            "value": "",  # Empty value for deletion
            "httponly": True,
            "secure": True,  # Only send over HTTPS in production
            "samesite": 'lax',  # Helps prevent CSRF attacks
            "max_age": 0,  # Immediate expiration (deletes cookie)
            "domain": None,  # Let browser use default (current domain)
            "path": '/',  # Make cookie available across the entire site
        }
        
        logger.debug("Generated cookie deletion config")
        return cookie_config
        
    except Exception as e:
        logger.error(f"Error in delete_auth_cookies: {e}", exc_info=True)
        # Return fallback deletion config
        return {
            "key": AUTH_COOKIE_KEY,
            "value": "",
            "httponly": True,
            "secure": True,
            "samesite": 'lax',
            "max_age": 0,  # Immediate expiration
            "domain": None,
            "path": '/',
        }


def generate_jwt_token(user_info: Dict[str, Any], platform: str, provider_name: str) -> str:
    """
    Generate a JWT token with user information.
    
    Args:
        user_info: Dictionary containing user information (id, email, name, etc.)
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        provider_name: The OAuth provider name (e.g., 'google', 'apple')
        
    Returns:
        str: JWT token string
    """
    # JWT token configuration
    jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key')
    jwt_algorithm = 'HS256'
    jwt_expire_hours = 24
    
    # Prepare token payload
    token_payload = {
        'sub': user_info.get('id', ''),
        'name': user_info.get('name', ''),
        'isAdmin': isUserAdmin(user_info.get('email', '')),
        'va-dir': getVaDir(user_info.get('id', ''), user_info.get('email', ''), provider_name),
        'platform': platform,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=jwt_expire_hours)
    }
    
    return jwt.encode(token_payload, jwt_secret, algorithm=jwt_algorithm)

def decode_jwt_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token and return the payload.
    
    Args:
        token: JWT token string to decode
        
    Returns:
        Dict[str, Any]: Decoded token payload
        
    Raises:
        jwt.JWTError: If token is invalid or expired
    """
    jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key')
    jwt_algorithm = 'HS256'
    
    return jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])


def isUserAdmin(email: str) -> bool:
    """
    Check if a user email is in the admin list.
    
    Args:
        email: User email to check
        
    Returns:
        bool: True if email is in admin list, False otherwise
    """
    admin_emails = os.getenv('ADMIN_EMAILS', '')
    admin_list = [email.strip() for email in admin_emails.split(',') if email.strip()]
    return email in admin_list

def getVaDir(user_id: str, email: str, provider: str) -> str:
    """
    Generate a VA(VoiceAssist) directory identifier by appending provider and id with underscore.
    
    Args:
        user_id: User ID to generate VA directory for
        email: User email to generate VA directory for
        provider: OAuth provider name (e.g., 'google', 'apple')
        
    Returns:
        str: VA directory identifier in format 'provider_id'
    """
    email_suffix = hash(email.replace('@', '_'))[:10] if email else hash(user_id)[:10]
    return f"{provider}_{user_id}_{email_suffix}"

def is_user_admin_from_token(token: str) -> bool:
    """
    Check if user is admin from JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        bool: True if user is admin, False otherwise
        
    Raises:
        jwt.JWTError: If token is invalid or expired
    """
    payload = decode_jwt_token(token)
    return payload.get('isAdmin', False)

def get_va_dir_from_token(token: str) -> str:
    """
    Get va-dir from JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        str: VA directory identifier
        
    Raises:
        jwt.JWTError: If token is invalid or expired
    """
    payload = decode_jwt_token(token)
    return payload.get('va-dir', '')

def extract_user_client_info(user_info: Dict[str, Any], platform: str, provider_name: str) -> Dict[str, Any]:
    """
    Extract and format user client information for display and processing.
    
    Args:
        user_info: Dictionary containing user information (id, email, name, etc.)
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        provider_name: The OAuth provider name (e.g., 'google', 'apple')
        
    Returns:
        Dict[str, Any]: Formatted user client information including display data
    """
    try:
        # Extract basic user information
        user_id = user_info.get('id', '')
        email = user_info.get('email', '')
        name = user_info.get('name', '')
        va_dir = getVaDir(user_id, email, provider_name)
        
        # Determine success messages based on platform and provider
        success_titles = {
            'web': "Web Authentication Successful",
            'ios': "iOS Authentication Successful", 
            'android': "Android Authentication Successful"
        }
        
        success_headings = {
            'google': f"Welcome {name}! You've successfully signed in with Google",
            'apple': f"Welcome {name}! You've successfully signed in with Apple",
            'microsoft': f"Welcome {name}! You've successfully signed in with Microsoft"
        }
        
        # Get platform-specific title or default
        success_html_title = success_titles.get(platform, "Authentication Successful")
        
        # Get provider-specific heading or fallback to generic
        success_html_heading = success_headings.get(provider_name, f"Welcome {name}! Authentication Successful")
        
        # Build the client info dictionary
        client_info = {
            "success_html_title": success_html_title,
            "success_html_heading": success_html_heading,
            "va-dir": va_dir,
            "Name": name,
            "Provider": provider_name,
            "Platform": platform,
            "User_ID": user_id,
        }
        
        logger.debug(f"Extracted client info for user {user_id}: {client_info}")
        return client_info
        
    except Exception as e:
        logger.error(f"Error in extract_user_client_info: {e}", exc_info=True)
        # Return fallback data
        return {
            "success_html_title": "Authentication Successful",
            "success_html_heading": "Authentication Successful",
            "va-dir": "",
            "Name": "",
            "Provider": provider_name,
            "Platform": platform,
            "User_ID": "",
        }

async def get_auth_context(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)), 
                          auth_token: str = Cookie(None, alias=AUTH_COOKIE_KEY)):
    """
    Dependency to extract authentication context from bearer token or cookie.
    
    Returns:
        Dict containing authentication information:
        - authenticated: bool - whether user is authenticated
        - va_dir: str - user's va-dir (DEFAULT_HASH_ID if not authenticated)
        - credentials: HTTPAuthorizationCredentials - raw credentials (None if not authenticated)
        - auth_source: str - 'bearer' or 'cookie' indicating auth method
    """
    payload = None
    try:
        # First try bearer token
        if credentials:
            logger.debug(f"Bearer token found: {credentials.credentials}")
            payload = decode_jwt_token(credentials.credentials)
            auth_source = 'bearer'
        if auth_token:
            logger.debug(f"Cookie found: {auth_token}")
            payload = decode_jwt_token(auth_token)
            auth_source = 'cookie'

        if payload:
            logger.debug(f"Payload found: {payload}")
            va_dir = payload.get('va-dir', '')
            isAdmin = payload.get('isAdmin', False)
            name = payload.get('name', '')
            user_id = payload.get('user_id', '')

            return {
                'authenticated': True,
                'va_dir': va_dir,
                'credentials': credentials,
                'auth_source': auth_source,
                'is_Admin' : isAdmin,
                'name' : name,
                'user_id' : user_id
            }
    except Exception as e:
            logger.error(f"Error extracting auth context from bearer: {str(e)}")
 
    # No valid authentication found
    return {
        'name' : '',
        'authenticated': False,
        'va_dir': 'default_user_123',  # DEFAULT_HASH_ID
        'credentials': None,
        'auth_source': 'none',
        'is_Admin' : False,
        'user_id' : ''
    }

def client_provided_storage_callback(user_info: Dict[str, Any], platform: str, provider_name: str) -> None:
    """
    Callback function to handle user data storage after successful authentication.
    
    Args:
        user_info: Dictionary containing user information (id, email, name, etc.)
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        provider_name: The OAuth provider name (e.g., 'google', 'apple')
    """
    try:
        # Extract relevant user data
        user_id = user_info.get('id', '')
        email = user_info.get('email', '')
        name = user_info.get('name', '')
        va_dir = getVaDir(user_id, email, provider_name)
        
        # Log user authentication for storage/analytics
        logger.info(f"User authenticated - ID: {user_id}, Email: {email}, Provider: {provider_name}, Platform: {platform}, VA-Dir: {va_dir}")
        
        # TODO: Implement actual storage logic here
        # This could involve:
        # - Storing user data in a database
        # - Calling external analytics services
        # - Updating user session storage
        # - Triggering business logic for new users
        
        # For now, we'll just log the authentication event
        if isUserAdmin(email):
            logger.info(f"Admin user authenticated: {email}")
            
    except Exception as e:
        logger.error(f"Error in client_provided_storage_callback: {e}", exc_info=True)
