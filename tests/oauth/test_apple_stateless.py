import os
import pytest
import time
from unittest.mock import patch, MagicMock, mock_open
from fastapi import HTTPException
from jose import jwt

from api.oauth.apple_stateless import (
    router,
    _normalize_platform,
    get_platform_client_config,
    get_oauth_provider,
    _load_apple_private_key,
    _build_apple_client_secret
)

@pytest.fixture
def mock_apple_config():
    return {
        "client_id": "com.test.app",
        "team_id": "test-team-id",
        "key_id": "test-key-id",
        "auth_key_path": "/path/to/key.p8",
        "token_endpoint": "https://appleid.apple.com/auth/token"
    }

class TestAppleStateless:
    def test_normalize_platform(self):
        """Test platform name normalization."""
        assert _normalize_platform("WEB") == "web"
        assert _normalize_platform("iOS") == "ios"
        assert _normalize_platform("AnDrOiD") == "android"
        assert _normalize_platform(None) == "web"
        assert _normalize_platform("") == "web"

    @patch('api.oauth.apple_stateless.get_auth_config')
    def test_get_platform_client_config(self, mock_get_config, mock_apple_config):
        """Test getting valid platform config."""
        mock_cfg = MagicMock()
        mock_cfg.client_id = "com.test.app"
        mock_cfg.authorization_endpoint = "https://appleid.apple.com/auth/authorize"
        mock_cfg.token_endpoint = "https://appleid.apple.com/auth/token"
        mock_cfg.team_id = "test-team-id"
        mock_cfg.key_id = "test-key-id"
        mock_cfg.auth_key_path = "/path/to/key.p8"
        mock_get_config.return_value = mock_cfg
        
        config = get_platform_client_config("ios", include_secrets=True)
        assert config["client_id"] == mock_apple_config["client_id"]
        assert config["team_id"] == mock_apple_config["team_id"]
        assert config["key_id"] == mock_apple_config["key_id"]
        assert config["auth_key_path"] == mock_apple_config["auth_key_path"]
        mock_get_config.assert_called_once_with("apple", "ios")

    @patch('api.oauth.apple_stateless.get_auth_config')
    def test_get_platform_client_config_missing(self, mock_get_config):
        """Test handling of missing platform config."""
        mock_get_config.side_effect = Exception("Config error")
        
        with pytest.raises(HTTPException) as exc_info:
            get_platform_client_config("invalid")
            
        assert exc_info.value.status_code == 500
        assert "not properly configured" in str(exc_info.value.detail)

    def test_state_cookie_encoding(self):
        """Test state cookie encoding and decoding."""
        state = "test-state-123"
        platform = "ios"
        
        provider = get_oauth_provider()
        encoded = provider._encode_state_cookie(state, platform)
        decoded = provider._decode_state_cookie(encoded)
        
        assert decoded["state"] == state
        assert decoded["platform"] == platform
        assert "iat" in decoded
        assert "exp" in decoded

    def test_load_apple_private_key(self, tmp_path):
        """Test loading Apple private key from file."""
        test_key = "-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----\n"
        key_path = tmp_path / "test_key.p8"
        key_path.write_text(test_key)
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.read_text', return_value=test_key):
                key_content = _load_apple_private_key(str(key_path))
                assert key_content == test_key

    @patch('api.oauth.apple_stateless.jwt.encode')
    @patch('time.time', return_value=1234567890)
    def test_build_apple_client_secret(self, mock_time, mock_jwt_encode, mock_apple_config):
        """Test building Apple client secret JWT."""
        # Mock the private key loading
        with patch('api.oauth.apple_stateless._load_apple_private_key', 
                  return_value="test-private-key"):
            _build_apple_client_secret(mock_apple_config)
            
            # Verify JWT encode was called with correct parameters
            mock_jwt_encode.assert_called_once()
            args, kwargs = mock_jwt_encode.call_args
            payload = args[0]
            
            assert payload["iss"] == mock_apple_config["team_id"]
            assert payload["sub"] == mock_apple_config["client_id"]
            assert payload["aud"] == "https://appleid.apple.com"
            assert payload["iat"] == 1234567890
            assert payload["exp"] == 1234569690  # iat + 1800
            assert kwargs["algorithm"] == "ES256"
            assert kwargs["headers"]["kid"] == mock_apple_config["key_id"]
