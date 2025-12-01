import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from api.auth_config import AuthConfig, AuthConfigManager, init_auth_config, get_auth_config

# Sample configuration data for testing
SAMPLE_GOOGLE_CONFIG = """
GOOGLE_CLIENT_ID=test-google-client-id
GOOGLE_CLIENT_SECRET=test-google-secret
GOOGLE_TOKEN_ENDPOINT=https://test-google-token-endpoint
"""

SAMPLE_APPLE_CONFIG = """
APPLE_CLIENT_ID=test-apple-client-id
APPLE_TEAM_ID=test-team-id
APPLE_KEY_ID=test-key-id
APPLE_AUTH_KEY_PATH=/path/to/key.p8
APPLE_TOKEN_ENDPOINT=https://test-apple-token-endpoint
"""
import debugpy
debugpy.listen(("0.0.0.0", 5678))
print("⏳ Remote debugger waiting for attach on port 5678...")
debugpy.wait_for_client()  # Pause until debugger attaches
print("✅ Remote debugger attached, continuing...")

@pytest.fixture
def temp_config_dir():
    """Create a temporary directory with test configuration files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test config files
        config_dir = Path(temp_dir) / "conf.d"
        config_dir.mkdir()
        
        # Create provider configs
        (config_dir / "google_web.env").write_text(SAMPLE_GOOGLE_CONFIG)
        (config_dir / "apple_ios.env").write_text(SAMPLE_APPLE_CONFIG)
        
        yield config_dir

class TestAuthConfig:
    def test_auth_config_creation(self):
        """Test basic AuthConfig creation with required fields."""
        config = AuthConfig(
            provider="test",
            platform="web",
            client_id="test-client",
            client_secret="test-secret",
            token_endpoint="https://test.com/token"
        )
        
        assert config.provider == "test"
        assert config.platform == "web"
        assert config.client_id == "test-client"
        assert config.client_secret == "test-secret"
        assert config.token_endpoint == "https://test.com/token"
        assert config.team_id is None
        assert config.key_id is None
        assert config.auth_key_path is None

    def test_auth_config_to_dict(self):
        """Test converting AuthConfig to dictionary."""
        config = AuthConfig(
            provider="test",
            platform="web",
            client_id="test-client",
            client_secret="test-secret",
            token_endpoint="https://test.com/token",
            team_id="test-team"
        )
        
        config_dict = config.to_dict()
        assert config_dict == {
            "provider": "test",
            "platform": "web",
            "client_id": "test-client",
            "client_secret": "test-secret",
            "token_endpoint": "https://test.com/token",
            "team_id": "test-team"
        }

class TestAuthConfigManager:
    def test_init_with_custom_dir(self, temp_config_dir):
        """Test initializing with a custom config directory."""
        manager = AuthConfigManager(base_dir=temp_config_dir)
        assert manager.base_dir == temp_config_dir
        
        # Should have loaded both configs
        assert "google" in manager._configs
        assert "apple" in manager._configs
        assert "web" in manager._configs["google"]
        assert "ios" in manager._configs["apple"]

    @patch.dict(os.environ, {"AUTH_CONFIG_DIR": "/custom/config/dir"})
    def test_init_with_env_var(self):
        """Test initializing with AUTH_CONFIG_DIR environment variable."""
        with patch("pathlib.Path.mkdir"):
            with patch("pathlib.Path.glob") as mock_glob:
                mock_glob.return_value = []
                manager = AuthConfigManager()
                assert str(manager.base_dir) == "/custom/config/dir"

    def test_get_auth_config_existing(self, temp_config_dir):
        """Test getting an existing auth config."""
        manager = AuthConfigManager(base_dir=temp_config_dir)
        config = manager.get_auth_config("google", "web")
        
        assert config.provider == "google"
        assert config.platform == "web"
        assert config.client_id == "test-google-client-id"
        assert config.client_secret == "test-google-secret"
        assert config.token_endpoint == "https://test-google-token-endpoint"

    def test_get_auth_config_nonexistent(self, temp_config_dir):
        """Test getting a non-existent auth config raises KeyError."""
        manager = AuthConfigManager(base_dir=temp_config_dir)
        
        with pytest.raises(KeyError) as exc_info:
            manager.get_auth_config("nonexistent", "web")
        assert "No nonexistent config found for platform 'web'" in str(exc_info.value)

    def test_reload_configs(self, temp_config_dir):
        """Test reloading configurations from disk."""
        manager = AuthConfigManager(base_dir=temp_config_dir)
        initial_configs = manager.get_all_configs()
        
        # Clear the configs and verify reload works
        manager._configs = {}
        manager.reload()
        
        assert manager.get_all_configs() != {}
        assert "google" in manager._configs
        assert "apple" in manager._configs

class TestModuleFunctions:
    def test_init_and_get_auth_config(self, temp_config_dir):
        """Test the module-level init_auth_config and get_auth_config functions."""
        with patch("api.auth_config.AuthConfigManager") as mock_manager:
            mock_instance = MagicMock()
            mock_manager.return_value = mock_instance
            
            # Test init
            manager = init_auth_config()
            assert manager == mock_instance
            
            # Test get_auth_config
            get_auth_config("test", "web")
            mock_instance.get_auth_config.assert_called_once_with("test", "web")
    
    def test_get_auth_config_before_init(self):
        """Test that get_auth_config raises RuntimeError if not initialized."""
        # Clear any existing auth config
        import api.auth_config as auth_config
        auth_config._auth_config = None
        
        with pytest.raises(RuntimeError) as exc_info:
            get_auth_config("test", "web")
        assert "AuthConfig has not been initialized" in str(exc_info.value)
