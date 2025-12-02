"""OAuth2.0 / OIDC integration package for FastAPI applications.

This package provides OAuth2.0 and OpenID Connect (OIDC) integration for FastAPI applications,
including support for multiple identity providers and platforms.
"""

from .config import (
    AuthConfig,
    AuthConfigManager,
    init_auth_config,
    get_auth_config,
    reload_auth_config
)

__all__ = [
    'AuthConfig',
    'AuthConfigManager',
    'init_auth_config',
    'get_auth_config',
    'reload_auth_config',
    # Add other public exports here
]
