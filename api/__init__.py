"""
VoiceAssistAPI - Core API package for the Voice Assistance Platform.

This package provides the main functionality for the Voice Assistance API,
including authentication, audio processing, and platform integrations.
"""

__version__ = "0.1.0"

# Import key components to make them available at the package level
from .auth_config import AuthConfig, get_auth_config, init_auth_config

# Initialize the auth configuration when the package is imported
init_auth_config()

__all__ = [
    'AuthConfig',
    'get_auth_config',
    'init_auth_config',
    '__version__',
]
