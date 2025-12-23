"""JWT utility functions for OAuth authentication."""
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from jose import jwt

def  generate_jwt_token(user_info: Dict[str, Any], platform: str) -> str:
    """
    Generate a JWT token with user information.
    
    Args:
        user_info: Dictionary containing user information (id, email, name, etc.)
        platform: The platform the user is authenticating from (e.g., 'web', 'ios', 'android')
        
    Returns:
        str: JWT token string
    """
    # JWT token configuration
    jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key')  # In production, use a strong secret from environment
    jwt_algorithm = 'HS256'
    jwt_expire_hours = 24  # Token expiry time in hours
    
    # Prepare token payload with standard claims
    token_payload = {
        'sub': user_info.get('id', ''),  # Subject (user ID)
        'email': user_info.get('email', ''),
        'name': user_info.get('name', ''),
        'platform': platform,
        'iat': datetime.now(timezone.utc),  # Issued at
        'exp': datetime.now(timezone.utc) + timedelta(hours=jwt_expire_hours)  # Expiration time
    }
    
    # Generate and return JWT token
    return jwt.encode(token_payload, jwt_secret, algorithm=jwt_algorithm)

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verify a JWT token and return its payload if valid.
    
    Args:
        token: JWT token to verify
        
    Returns:
        Dict containing the token payload if verification succeeds
        
    Raises:
        JWTError: If token verification fails
    """
    jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key')
    return jwt.decode(token, jwt_secret, algorithms=['HS256'])
