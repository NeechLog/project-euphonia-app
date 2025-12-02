import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from api.oauth.google_stateless import router, _normalize_platform, _get_platform_config
from api.oauth import get_auth_config

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
        mock_get_config.return_value = mock_google_config
        
        config = _get_platform_config("web")
        assert config == mock_google_config
        mock_get_config.assert_called_once_with("google", "web")

    @patch('api.oauth.google_stateless.get_auth_config')
    def test_get_platform_config_missing(self, mock_get_config):
        """Test handling of missing platform config."""
        mock_get_config.side_effect = KeyError("Config not found")
        
        with pytest.raises(HTTPException) as exc_info:
            _get_platform_config("invalid")
            
        assert exc_info.value.status_code == 500
        assert "not properly configured" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch('api.oauth.google_stateless.requests.post')
    @patch('api.oauth.google_stateless._get_platform_config')
    async def test_token_exchange_success(self, mock_get_config, mock_post, mock_google_config):
        """Test successful token exchange."""
        # Setup mocks
        mock_get_config.return_value = mock_google_config
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "test-token"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Test the endpoint
        from api.oauth.google_stateless import exchange_code
        response = await exchange_code(
            code="test-code",
            redirect_uri="https://test.com/callback",
            platform="web"
        )
        
        assert response == {"access_token": "test-token"}
        mock_post.assert_called_once()
