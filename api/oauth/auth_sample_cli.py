#!/usr/bin/env python3
"""
Command-line utility for testing OAuth authentication flows.

Usage:
    python -m api.oauth.cli.auth_sample_cli --help
"""
import debugpy
debugpy.listen(("0.0.0.0", 5678))
debugpy.wait_for_client()

import os
import sys
import json
import argparse
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
from typing import Dict, Any, Optional

import httpx

# Import and initialize auth config
from ..auth_config import init_auth_config, get_auth_config, AuthConfig
init_auth_config()

def get_oauth_config(provider: str, platform: str) -> Dict[str, Any]:
    """
    Get OAuth configuration for the specified provider and platform.
    
    Args:
        provider: OAuth provider (e.g., 'google', 'apple')
        platform: Target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        dict: Configuration including auth_url, token_url, and other OAuth settings
    """
    try:
        config = get_auth_config(provider, platform)
        
        # Common OAuth endpoints
        base_config = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "token_endpoint": config.token_endpoint,
            "auth_url": f"https://{'accounts.google.com' if provider == 'google' else 'appleid.apple.com'}/{'o/oauth2/v2/auth' if provider == 'google' else 'auth/authorize'}",
            "redirect_uri": f"http://localhost:8000/auth/{provider}/callback",
            "scopes": ["openid", "email", "profile"] if provider == "google" else ["email", "name"]
        }
        
        # Add provider-specific configurations
        if provider == "apple":
            base_config.update({
                "team_id": config.team_id,
                "key_id": config.key_id,
                "auth_key_path": config.auth_key_path
            })
            
        return base_config
    except Exception as e:
        print(f"Error loading {provider} config: {e}")
        raise

# Default configuration (fallback if auth config is not available)
DEFAULT_CONFIG = {
    "google": get_oauth_config("google", "web") if os.getenv("GOOGLE_CLIENT_ID") else {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "http://localhost:8000/auth/google/token",
        "redirect_uri": "http://localhost:8000/auth/google/callback",
        "scopes": ["openid", "email", "profile"]
    },
    "apple": get_oauth_config("apple", "web") if os.getenv("APPLE_CLIENT_ID") else {
        "auth_url": "https://appleid.apple.com/auth/authorize",
        "token_url": "http://localhost:8000/auth/apple/token",
        "redirect_uri": "http://localhost:8000/auth/apple/callback",
        "scopes": ["email", "name"]
    }
}

def get_auth_url(provider: str, client_id: str, platform: str = "web") -> str:
    """Generate OAuth authorization URL."""
    config = DEFAULT_CONFIG.get(provider.lower())
    if not config:
        raise ValueError(f"Unsupported provider: {provider}")
    
    params = {
        "client_id": client_id,
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(config["scopes"]),
        "state": f"{provider}_{platform}",
    }
    
    # Apple-specific parameters
    if provider.lower() == "apple":
        params["response_mode"] = "form_post"
    
    return f"{config['auth_url']}?{urlencode(params)}"

async def exchange_code(provider: str, code: str, platform: str = "web") -> dict:
    """Exchange authorization code for tokens."""
    config = DEFAULT_CONFIG.get(provider.lower())
    if not config:
        raise ValueError(f"Unsupported provider: {provider}")
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config["redirect_uri"],
        "platform": platform
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            config["token_url"],
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        return response.json()

async def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Test OAuth authentication flows")
    parser.add_argument("provider", choices=["google", "apple"], help="OAuth provider")
    parser.add_argument("--client-id", help="OAuth client ID")
    parser.add_argument("--platform", default="web", choices=["web", "ios", "android"], 
                      help="Platform type")
    parser.add_argument("--code", help="Authorization code for token exchange")
    
    args = parser.parse_args()
    
    if not args.code:
        # Generate and open auth URL
        client_id = args.client_id or os.getenv(f"{args.provider.upper()}_CLIENT_ID")
        if not client_id:
            print(f"Error: No client ID provided and {args.provider.upper()}_CLIENT_ID not set in .env")
            sys.exit(1)
            
        auth_url = get_auth_url(args.provider, client_id, args.platform)
        print(f"Opening auth URL in browser: {auth_url}")
        webbrowser.open(auth_url)
        print("After authorizing, run this script again with the code parameter.")
    else:
        # Exchange code for tokens
        try:
            tokens = await exchange_code(args.provider, args.code, args.platform)
            print("\nAuthentication successful!")
            print("\nTokens received:")
            print(json.dumps(tokens, indent=2))
        except Exception as e:
            print(f"\nError during token exchange: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
