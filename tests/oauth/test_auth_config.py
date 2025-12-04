import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Define test config directory path
TEST_CONFIG_DIR = Path(__file__).parent.parent / "test_configs"
from api.oauth.config import AuthConfig, AuthConfigManager
from api.oauth.config import init_auth_config, get_auth_config

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

@pytest.fixture
def temp_config_dir():
    """Create a temporary directory with test configuration files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test config files
        (temp_path / "google_web.env").write_text(SAMPLE_GOOGLE_CONFIG)
        (temp_path / "apple_ios.env").write_text(SAMPLE_APPLE_CONFIG)
        
        # Create an empty directory for testing missing configs
        (temp_path / "empty").mkdir()
        
        yield temp_path

class TestAuthConfig:
    """Test the AuthConfig class."""
    
    def test_auth_config_creation(self):
        """Test basic AuthConfig creation with required fields."""
        config = AuthConfig(
            provider="test-provider",
            platform="test-platform",
            client_id="test-client-id",
            client_secret="test-secret",
            token_endpoint="https://test-token-endpoint"
        )
        
        assert config.provider == "test-provider"
        assert config.platform == "test-platform"
        assert config.client_id == "test-client-id"
        assert config.client_secret == "test-secret"
        assert config.token_endpoint == "https://test-token-endpoint"
    
    def test_auth_config_to_dict(self):
        """Test converting AuthConfig to dictionary."""
        config = AuthConfig(
            provider="test-provider",
            platform="test-platform",
            client_id="test-client-id",
            client_secret="test-secret",
            token_endpoint="https://test-token-endpoint",
            team_id="test-team-id"
        )
        
        config_dict = config.to_dict()
        assert config_dict == {
            "provider": "test-provider",
            "platform": "test-platform",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
            "token_endpoint": "https://test-token-endpoint",
            "team_id": "test-team-id",
            "key_id": None,
            "auth_key_path": None
        }

class TestAuthConfigManager:
    """Test the AuthConfigManager class."""
    
    def test_init_with_custom_dir(self, temp_config_dir):
        """Test initializing with a custom config directory."""
        manager = AuthConfigManager(temp_config_dir)
        assert manager.base_dir == temp_config_dir
        assert "google" in manager._configs
        assert "web" in manager._configs["google"]
        assert "apple" in manager._configs
        assert "ios" in manager._configs["apple"]
    
    @patch.dict(os.environ, {"AUTH_CONFIG_DIR": "/test/config/dir"})
    def test_init_with_env_var(self):
        """Test initializing with AUTH_CONFIG_DIR environment variable."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.glob') as mock_glob:
                mock_glob.return_value = []
                manager = AuthConfigManager()
                assert str(manager.base_dir) == "/test/config/dir"
    
    def test_get_auth_config_existing(self, temp_config_dir):
        """Test getting an existing auth config."""
        manager = AuthConfigManager(temp_config_dir)
        config = manager.get_auth_config("google", "web")
        
        assert config.provider == "google"
        assert config.platform == "web"
        assert config.client_id == "test-google-client-id"
        assert config.client_secret == "test-google-secret"
    
    def test_get_auth_config_nonexistent(self, temp_config_dir):
        """Test getting a non-existent auth config raises KeyError."""
        manager = AuthConfigManager(temp_config_dir)
        with pytest.raises(KeyError):
            manager.get_auth_config("nonexistent", "platform")
    
    def test_reload_configs(self, temp_config_dir):
        """Test reloading configurations from disk."""
        manager = AuthConfigManager(temp_config_dir)
        initial_count = len(manager._configs)
        
        # Add a new config file
        new_config = temp_config_dir / "new_provider_android.env"
        new_config.write_text("CLIENT_ID=new-client\nCLIENT_SECRET=new-secret\nTOKEN_ENDPOINT=https://new-endpoint")
        
        manager.reload()
        
        assert len(manager._configs) == initial_count + 1
        assert "new_provider" in manager._configs
        assert "android" in manager._configs["new_provider"]

class TestModuleFunctions:
    """Test the module-level functions."""
    
    def test_init_and_get_auth_config(self, temp_config_dir):
        """Test the module-level init_auth_config and get_auth_config functions."""
        # Initialize with test config directory
        manager = init_auth_config(temp_config_dir)
        
        # Get config using module function
        config = get_auth_config("google", "web")
        
        assert config.provider == "google"
        assert config.platform == "web"
        assert config.client_id == "test-google-client-id"
    
    def test_get_auth_config_before_init(self):
        """Test that get_auth_config raises RuntimeError if not initialized."""
        # Reset the global _auth_config
        import sys
        if 'api.oauth.config' in sys.modules:
            sys.modules['api.oauth.config']._auth_config = None
        
        with pytest.raises(RuntimeError) as excinfo:
            get_auth_config("google", "web")
        assert "AuthConfig has not been initialized" in str(excinfo.value)
