"""
VoiceAssistAPI - Core API package for the Voice Assistance Platform.

This package provides the main functionality for the Voice Assistance API,
including authentication, audio processing, and platform integrations.
"""
from .oauth.jwt_utils import generate_jwt_token, verify_jwt_token
from .oauth.base_oauth import OAuthProvider

# Import specific OAuth providers if they exist
try:
    from .oauth.google_stateless import GoogleOAuthProvider
    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    GOOGLE_OAUTH_AVAILABLE = False

__version__ = "0.1.0"

# Export public API
__all__ = [
    'generate_jwt_token',
    'verify_jwt_token',
    'OAuthProvider',
]

# Conditionally export Google OAuth provider if available
if GOOGLE_OAUTH_AVAILABLE:
    __all__.append('GoogleOAuthProvider')

