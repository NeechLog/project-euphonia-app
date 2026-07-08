import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
import httpx

from api.oauth.google_stateless import (
    router,
    _normalize_platform,
    get_platform_config,
    _exchange_code_for_tokens,
)
from api.oauth.config import get_auth_config

@pytest.fixture
def mock_google_config():
    return {
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "token_endpoint": "https://test-token-endpoint"
    }

class TestGoogleStateless:
    def test_normalize_platform(self):
        """Test platform name normalization."""
        assert _normalize_platform("WEB") == "web"
        assert _normalize_platform("iOS") == "ios"
        assert _normalize_platform("AnDrOiD") == "android"
        assert _normalize_platform(None) == "web"
        assert _normalize_platform("") == "web"

    @patch('api.oauth.google_stateless.get_auth_config')
    def test_get_platform_config_valid(self, mock_get_config, mock_google_config):
        """Test getting valid platform config."""
        mock_cfg = MagicMock()
        mock_cfg.client_id = "test-client-id"
        mock_cfg.web_client_id = "test-web-client-id"
        mock_cfg.authorization_endpoint = "https://auth"
        mock_cfg.token_endpoint = "https://test-token-endpoint"
        mock_cfg.userinfo_endpoint = "https://userinfo"
        mock_cfg.scope = "scope"
        mock_cfg.redirect_uri = "https://redirect"
        mock_cfg.client_secret = "test-secret"

        mock_get_config.return_value = mock_cfg

        config = get_platform_config("web", include_secrets=True)
        assert config["client_id"] == "test-client-id"
        assert config["client_secret"] == "test-secret"
        mock_get_config.assert_called_once_with("google", "web")

    @patch('api.oauth.google_stateless.get_auth_config')
    def test_get_platform_config_missing(self, mock_get_config):
        """Test handling of missing platform config."""
        mock_get_config.side_effect = Exception("Config not found")

        with pytest.raises(HTTPException) as exc_info:
            get_platform_config("invalid")

        assert exc_info.value.status_code == 500
        assert "not properly configured" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch('api.oauth.google_stateless.httpx.AsyncClient')
    async def test_token_exchange_success(self, mock_async_client, mock_google_config):
        """Test successful token exchange."""
        # Setup mocks
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "test-token"}
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_client_context = MagicMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=None)

        mock_async_client.return_value = mock_client_context

        # Test the helper function
        response = await _exchange_code_for_tokens(
            code="test-code",
            redirect_uri="https://test.com/callback",
            client_config=mock_google_config
        )
        
        assert response == {"access_token": "test-token"}
        mock_client.post.assert_called_once()
