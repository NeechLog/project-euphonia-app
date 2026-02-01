import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Any, Type, TypeVar, Generic, TypedDict, List, Callable
import logging


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
    scope: str = "openid email profile"  # Default scope for most OAuth providers
    web_client_id: Optional[str] = None
    team_id: Optional[str] = None
    key_id: Optional[str] = None
    auth_key_path: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    redirect_uri: Optional[str] = None
    deep_link_scheme: Optional[str] = None  # Deep link scheme for mobile redirects (e.g., "voiceassistance")
    storage_callback: Optional[Callable[[Dict[str, Any], str, str], None]] = None
    client_info_extractor: Optional[Callable[[Dict[str, Any], str, str], Dict[str, Any]]] = None 
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the config to a dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuthConfig':
        """Create an AuthConfig from a dictionary."""
        return cls(**data)

class AuthConfigManager:
    """
    Manages authentication configurations loaded from environment files.
    
    Looks for files in the format: {provider}_{platform}.env in the config directory.
    Example: google_web.env, apple_ios.env
    """
    
    def __init__(
        self, 
        base_dir: Optional[Path] = None,
        token_generator_func: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
        storage_callback: Optional[Callable[[Dict[str, Any], str, str], None]] = None,
        client_info_extractor: Optional[Callable[[Dict[str, Any], str, str], Dict[str, Any]]] = None,
        cookie_generator_func: Optional[Callable[[str, str, str], Dict[str, Any]]] = None,
        cookie_remover_func: Optional[Callable[[], Dict[str, Any]]] = None
    ):
        # Pick directory from env, with a sensible default
        if base_dir is None:
            env_dir = os.getenv("AUTH_CONFIG_DIR")
            if env_dir:
                base_dir = Path(env_dir).expanduser().resolve()
            else:
                # default to project_root/conf.d (parallel to api and infra)
                project_root = Path(__file__).resolve().parent.parent.parent
                base_dir = project_root / "conf.d"
        
        self.base_dir = base_dir
        self.token_generator_func = token_generator_func
        self.storage_callback = storage_callback
        self.client_info_extractor = client_info_extractor
        self.cookie_generator_func = cookie_generator_func
        self.cookie_remover_func = cookie_remover_func
        self._configs: Dict[str, Dict[str, AuthConfig]] = {}
        self._load_all_configs()
    
    def _load_env_file(self, path: Path) -> Dict[str, str]:
        """Load key-value pairs from an environment file."""
        if not path.exists():
            return {}
            
        env_vars = {}
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"\'')
        return env_vars
    
    def _parse_config_filename(self, filename: str) -> tuple[str, str]:
        """Parse provider and platform from filename (e.g., google_web.env -> (google, web))."""
        filename_lower = filename.lower()
        if not (filename_lower.endswith('.env') or filename_lower.endswith('.env.example')):
            return None, None
            
        # Remove extensions manually to handle .env.example correctly
        base_name = filename
        if filename_lower.endswith('.env.example'):
            base_name = base_name[:-12]  # Remove .env.example
        elif filename_lower.endswith('.env'):
            base_name = base_name[:-4]   # Remove .env
            
        parts = base_name.split('_', 1)
        if len(parts) != 2:
            return None, None
            
        provider, platform = parts[0].lower(), parts[1].lower()
        
        # Validate that both provider and platform are non-empty
        if not provider or not platform:
            return None, None
            
        return provider, platform
    
    def _load_all_configs(self):
        """Load all configuration files from the config directory."""
        if not self.base_dir.exists():
            logging.warning(f"Config directory not found: {self.base_dir}")
            return
            
        for file_path in self.base_dir.glob('*.env*'):
            provider, platform = self._parse_config_filename(file_path.name)
            if provider and platform:
                self._load_config(file_path, provider, platform)
    
    def _load_config(self, file_path: Path, provider: str, platform: str):
        """Load and validate a single config file."""
        env_vars = self._load_env_file(file_path)
        
        if not env_vars:
            logging.warning(f"Empty or invalid config file: {file_path}")
            return
            
        # Get the token endpoint with appropriate defaults
        token_endpoint = self._get_token_endpoint(provider, env_vars)
        ## TODO: look at https://github.com/NeechLog/project-euphonia-app/issues/19
        # Create the config object
        config = AuthConfig(
            provider=provider,
            platform=platform,
            client_id=env_vars.get('client_id', ''),
            web_client_id=env_vars.get('web_client_id', ''),
            client_secret=env_vars.get('client_secret', ''),
            token_endpoint=token_endpoint,
            scope=env_vars.get('SCOPE', 'openid email profile'),
            team_id=env_vars.get('TEAM_ID'),
            key_id=env_vars.get('KEY_ID'),
            authorization_endpoint=env_vars.get('auth_uri'),
            redirect_uri=env_vars.get('redirect_uri'),
            deep_link_scheme=env_vars.get('DEEP_LINK_SCHEME'),
            auth_key_path=env_vars.get('AUTH_KEY_PATH'),
            storage_callback=self.storage_callback,
            client_info_extractor=self.client_info_extractor
        )
        
        # Store the config
        if provider not in self._configs:
            self._configs[provider] = {}
        self._configs[provider][platform] = config
        
        logging.debug(f"Loaded config for {provider} ({platform}) from {file_path}")
    
    def _get_token_endpoint(self, provider: str, env_vars: Dict[str, str]) -> str:
        """Get the token endpoint with appropriate defaults."""
        if 'token_uri' in env_vars:
            return env_vars['token_uri']
            
        # Default token endpoints for common providers
        defaults = {
            'google': 'https://oauth2.googleapis.com/token',
            'apple': 'https://appleid.apple.com/auth/token',
            'microsoft': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            'github': 'https://github.com/login/oauth/access_token'
        }
        
        return defaults.get(provider.lower(), '')
    
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
        except KeyError:
            raise KeyError(
                f"No configuration found for provider '{provider}' and platform '{platform}'. "
                f"Available providers: {list(self._configs.keys())}"
            )
    
    def get_token_generator_func(self) -> Optional[Callable[[Dict[str, Any], str, str], str]]:
        """Get the token generator function."""
        return self.token_generator_func
    
    def get_storage_func(self) -> Optional[Callable[[Dict[str, Any], str, str], None]]:
        """Get the storage function."""
        return self.storage_callback
    
    def get_user_info_func(self) -> Optional[Callable[[Dict[str, Any], str, str], Dict[str, Any]]]:
        """Get the user info extractor function."""
        return self.client_info_extractor
    
    def get_cookie_generator_func(self) -> Optional[Callable[[str, str, str], Dict[str, Any]]]:
        """Get the cookie generator function."""
        return self.cookie_generator_func
    
    def get_cookie_remover_func(self) -> Optional[Callable[[], Dict[str, Any]]]:
        """Get the cookie remover function."""
        return self.cookie_remover_func
    
    def get_all_configs(self) -> Dict[str, Dict[str, AuthConfig]]:
        """Get all loaded configurations."""
        return self._configs
    
    def reload(self):
        """Reload all configurations from disk."""
        self._configs = {}
        self._load_all_configs()

# Global instance
_auth_config: Optional[AuthConfigManager] = None

def init_auth_config(
    base_dir: Optional[Path] = None,
    token_generator_func: Optional[Callable[[Dict[str, Any], str, str], str]] = None,
    storage_callback: Optional[Callable[[Dict[str, Any], str, str], None]] = None,
    client_info_extractor: Optional[Callable[[Dict[str, Any], str, str], Dict[str, Any]]] = None,
    cookie_generator_func: Optional[Callable[[str, str, str], Dict[str, Any]]] = None,
    cookie_remover_func: Optional[Callable[[], Dict[str, Any]]] = None
) -> AuthConfigManager:
    """Initialize and return the global AuthConfigManager instance.
    
    Args:
        base_dir: Optional base directory to look for config files. If not provided,
                 will use AUTH_CONFIG_DIR environment variable or default to project_root/conf.d
        token_generator_func: Optional function to generate JWT tokens. If not provided,
                             will use the default generate_jwt_token function
        storage_callback: Optional function to handle user data storage after authentication
        client_info_extractor: Optional function to extract user client information for display
        cookie_generator_func: Optional function to generate cookie configuration for secure cookies
        cookie_remover_func: Optional function to generate cookie configuration for removing cookies
    """
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfigManager(
            base_dir=base_dir, 
            token_generator_func=token_generator_func,
            storage_callback=storage_callback,
            client_info_extractor=client_info_extractor,
            cookie_generator_func=cookie_generator_func,
            cookie_remover_func=cookie_remover_func
        )
        logging.info("AuthConfig initialized successfully")
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
        raise RuntimeError(
            "AuthConfig has not been initialized. Call init_auth_config() first."
        )
    return _auth_config.get_auth_config(provider, platform)

def reload_auth_config() -> None:
    """Reload all authentication configurations from disk."""
    if _auth_config is not None:
        _auth_config.reload()
        logging.info("AuthConfig reloaded successfully")
    else:
        logging.warning("Cannot reload AuthConfig: not initialized")


def main():
    """Main function for debugging and testing the AuthConfigManager."""
    # Set up logging for debug session
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Handle AUTH_CONFIG_DIR parameter
    if len(sys.argv) > 1:
        auth_config_dir = sys.argv[1]
        print(f"Setting AUTH_CONFIG_DIR to: {auth_config_dir}")
        os.environ["AUTH_CONFIG_DIR"] = auth_config_dir
    else:
        # Use default if not provided
        project_root = Path(__file__).resolve().parent.parent.parent
        default_dir = project_root / "conf.d"
        os.environ["AUTH_CONFIG_DIR"] = str(default_dir)
        print(f"Using default AUTH_CONFIG_DIR: {default_dir}")
    
    print(f"Current AUTH_CONFIG_DIR environment variable: {os.getenv('AUTH_CONFIG_DIR')}")
    
    try:
        # Initialize the AuthConfigManager
        print("\n=== Initializing AuthConfigManager ===")
        config_manager = init_auth_config()
        
        # Debug session: Display loaded configurations
        print("\n=== Debug Session: Loaded Configurations ===")
        all_configs = config_manager.get_all_configs()
        
        if not all_configs:
            print("No configurations found!")
        else:
            for provider, platforms in all_configs.items():
                print(f"\nProvider: {provider}")
                for platform, config in platforms.items():
                    config_dict = config.to_dict()
                    for key, value in config_dict.items():
                        if value is not None:
                            print(f"    {key}: {value}")
        
        # Test getting specific configurations
        print("\n=== Testing Configuration Retrieval ===")
        for provider in ['google', 'apple']:
            for platform in ['web', 'ios']:
                try:
                    config = config_manager.get_auth_config(provider, platform)
                    print(f"✓ Successfully retrieved {provider}_{platform} config")
                except KeyError as e:
                    print(f"✗ Could not retrieve {provider}_{platform} config: {e}")
        
        print("\n=== Debug Session Complete ===")
        
    except Exception as e:
        print(f"Error during debug session: {e}")
        logging.exception("Detailed error information:")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
