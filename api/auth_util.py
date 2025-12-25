"""Authentication utilities for token generation and validation."""
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from jose import jwt

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

def getVaDir(user_id: str, provider: str) -> str:
    """
    Generate a VA(VoiceAssist) directory identifier by appending provider and id with underscore.
    
    Args:
        user_id: User ID to generate VA directory for
        provider: OAuth provider name (e.g., 'google', 'apple')
        
    Returns:
        str: VA directory identifier in format 'provider_id'
    """
    return f"{provider}_{user_id}"

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
        'va-dir': getVaDir(user_info.get('id', ''), provider_name),
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

def client_provided_storage_callback(user_info: Dict[str, Any], platform: str, provider_name: str) -> None:
    """
    Callback function to handle user data storage after successful authentication.
    
    Args:
        user_info: Dictionary containing user information (id, email, name, etc.)
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        provider_name: The OAuth provider name (e.g., 'google', 'apple')
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract relevant user data
        user_id = user_info.get('id', '')
        email = user_info.get('email', '')
        name = user_info.get('name', '')
        va_dir = getVaDir(user_id, provider_name)
        
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
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract basic user information
        user_id = user_info.get('id', '')
        email = user_info.get('email', '')
        name = user_info.get('name', '')
        va_dir = getVaDir(user_id, provider_name)
        
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
