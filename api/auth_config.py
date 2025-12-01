import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Any, Type, TypeVar, Generic, TypedDict, List

T = TypeVar('T')

class AuthConfigData(TypedDict):
    """Type hint for raw auth configuration data."""
    provider: str
    platform: str
    client_id: str
    client_secret: str
    token_endpoint: str
    # Additional provider-specific fields
    team_id: Optional[str]
    key_id: Optional[str]
    auth_key_path: Optional[str]


@dataclass
class AuthConfig:
    """
    Generic authentication configuration for any provider.
    """
    provider: str
    platform: str
    client_id: str
    client_secret: str
    token_endpoint: str
    # Additional provider-specific fields
    team_id: Optional[str] = None
    key_id: Optional[str] = None
    auth_key_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert config to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> 'AuthConfig':
        """Create AuthConfig from dictionary, ignoring extra fields."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class AuthConfigManager:
    """
    Manages authentication configurations loaded from environment files.
    
    Looks for files in the format: {provider}_{platform}.env in the config directory.
    Example: google_web.env, apple_ios.env
    """
    def __init__(self, base_dir: Optional[Path] = None):
        # Pick directory from env, with a sensible default
        if base_dir is None:
            env_dir = os.getenv("AUTH_CONFIG_DIR")
            if env_dir:
                base_dir = Path(env_dir).expanduser().resolve()
            else:
                # default to project_root/conf.d (parallel to api and infra)
                project_root = Path(__file__).resolve().parent.parent
                base_dir = project_root / "conf.d"

        self.base_dir = base_dir
        self._configs: Dict[str, Dict[str, AuthConfig]] = {}
        self._load_all_configs()

    def _load_env_file(self, path: Path) -> Dict[str, str]:
        """Load key-value pairs from an environment file."""
        if not path.exists():
            return {}
            
        result: Dict[str, str] = {}
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip().strip("\"'")
        return result

    def _parse_config_filename(self, filename: str) -> tuple[str, str] | None:
        """Parse provider and platform from filename (e.g., google_web.env -> (google, web))."""
        if not filename.endswith('.env'):
            return None
            
        name = filename[:-4]  # Remove .env
        parts = name.split('_')
        if len(parts) < 2:
            return None
            
        provider = parts[0].lower()
        platform = '_'.join(parts[1:]).lower()  # Handle multi-part platform names
        return provider, platform

    def _load_all_configs(self) -> None:
        """Load all configuration files from the config directory."""
        if not self.base_dir.exists():
            return
            
        for file_path in self.base_dir.glob('*.env'):
            result = self._parse_config_filename(file_path.name)
            if not result:
                continue
                
            provider, platform = result
            config_data = self._load_config(file_path, provider, platform)
            if config_data:
                self._configs.setdefault(provider, {})[platform] = config_data

    def _load_config(self, file_path: Path, provider: str, platform: str) -> Optional[AuthConfig]:
        """Load and validate a single config file."""
        env_vars = self._load_env_file(file_path)
        if not env_vars:
            return None

        # Build config dictionary with provider/type information
        config_data: Dict[str, Any] = {
            'provider': provider,
            'platform': platform,
            'client_id': env_vars.get(f'{provider.upper()}_CLIENT_ID', ''),
            'client_secret': env_vars.get(f'{provider.upper()}_CLIENT_SECRET', ''),
            'token_endpoint': self._get_token_endpoint(provider, env_vars),
        }

        # Add provider-specific fields
        if provider.lower() == 'apple':
            config_data.update({
                'team_id': env_vars.get('APPLE_TEAM_ID', ''),
                'key_id': env_vars.get('APPLE_KEY_ID', ''),
                'auth_key_path': env_vars.get('APPLE_AUTH_KEY_PATH', '')
            })

        # Skip if required fields are missing
        if not config_data['client_id']:
            return None

        return AuthConfig.from_dict(config_data)

    def _get_token_endpoint(self, provider: str, env_vars: Dict[str, str]) -> str:
        """Get the token endpoint with appropriate defaults."""
        default_endpoints = {
            'google': 'https://oauth2.googleapis.com/token',
            'apple': 'https://appleid.apple.com/auth/token',
        }
        
        # Check for provider-specific token endpoint in environment
        env_key = f'{provider.upper()}_TOKEN_ENDPOINT'
        if env_key in os.environ:
            return os.environ[env_key]
            
        # Check in the loaded env file
        if env_key in env_vars:
            return env_vars[env_key]
            
        # Fall back to default
        return default_endpoints.get(provider.lower(), '')

    def get_auth_config(self, provider: str, platform: str) -> AuthConfig:
        """
        Get authentication configuration for the specified provider and platform.
        
        Args:
            provider: Authentication provider (e.g., 'google', 'apple')
            platform: Target platform (e.g., 'web', 'ios', 'android')
            
        Returns:
            AuthConfig: The configuration for the specified provider and platform
            
        Raises:
            KeyError: If the configuration is not found
        """
        provider = provider.lower()
        platform = platform.lower()
        
        try:
            return self._configs[provider][platform]
        except KeyError as e:
            raise KeyError(
                f"No {provider} config found for platform '{platform}' in {self.base_dir}. "
                f"Available configs: {list(self._configs.keys())}"
            ) from e
            
    def get_all_configs(self) -> Dict[str, Dict[str, AuthConfig]]:
        """Get all loaded configurations."""
        return self._configs.copy()
        
    def reload(self) -> None:
        """Reload all configurations from disk."""
        self._configs.clear()
        self._load_all_configs()


_auth_config: Optional[AuthConfigManager] = None


def init_auth_config() -> AuthConfigManager:
    """Initialize and return the global AuthConfigManager instance."""
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfigManager()
    return _auth_config


def get_auth_config(provider: str, platform: str) -> AuthConfig:
    """
    Get authentication configuration for the specified provider and platform.
    
    Args:
        provider: Authentication provider (e.g., 'google', 'apple')
        platform: Target platform (e.g., 'web', 'ios', 'android')
        
    Returns:
        AuthConfig: The configuration for the specified provider and platform
        
    Raises:
        RuntimeError: If the auth config has not been initialized
        KeyError: If the requested configuration is not found
    """
    if _auth_config is None:
        raise RuntimeError("AuthConfig has not been initialized. Call init_auth_config() first.")
    return _auth_config.get_auth_config(provider, platform)


def reload_auth_config() -> None:
    """Reload all authentication configurations from disk."""
    if _auth_config is not None:
        _auth_config.reload()
