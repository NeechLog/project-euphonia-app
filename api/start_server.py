#!/usr/bin/env python3
"""
Start script for the Uvicorn server.
Usage: python3 start_server.py
"""
import os
import signal
import sys
import uvicorn
from pathlib import Path
from uvicorn.config import Config
from uvicorn import Server
from uvicorn_config import UVICORN_CONFIG, get_pid_file_path
from api.oauth import init_auth_config

def load_env(filepath='.env.oidc.example'):
    """
    Load environment variables from a .env file.
    
    Args:
        filepath (str): Path to the .env file. Defaults to '.env.oidc' in the same directory.
    """
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    # Split on first '=' only
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"\'')
        print(f"Loaded environment variables from {filepath}")
        return True
    except FileNotFoundError:
        print(f"Warning: {filepath} not found. Using system environment variables.")
        return False
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return False

# Load environment variables from .env.oidc if it exists
env_path = Path(__file__).parent / '.env.oidc'
load_env(env_path)

def write_pid(pid_file):
    """Write the current process ID to the PID file."""
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except IOError as e:
        print(f"Error writing PID file: {e}", file=sys.stderr)
        return False

def cleanup_pid(pid_file):
    """Remove the PID file if it exists."""
    try:
        pid_path = Path(pid_file)
        if pid_path.exists():
            pid_path.unlink()
    except Exception as e:
        print(f"Error cleaning up PID file: {e}", file=sys.stderr)

def handle_exit(sig, frame):
    """Handle exit signals."""
    print("\nShutting down server...")
    cleanup_pid("uvicorn.pid")
    sys.exit(0)

def start_server():
    """Start the Uvicorn server with the specified configuration."""
    pid_file = get_pid_file_path()
    try:
        init_auth_config()
        print("AuthConfig initialized successfully")
    except Exception as e:
        print(f"Error initializing AuthConfig: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Write PID file first - if this fails, we shouldn't proceed
    if not write_pid(pid_file):
        print("Failed to write PID file. Exiting.", file=sys.stderr)
        sys.exit(1)
    pid_path = Path(pid_file)
    if not pid_path.exists():
        print("PID file does not exist. Exiting.", file=sys.stderr)
        sys.exit(1)
    # Set up signal handlers after PID file is written
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    pid = os.getpid()
    print(f"Starting server on {UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
    print(f"Workers: {UVICORN_CONFIG.get('workers', 1)}")
    print(f"Process ID: {pid} | PID file: {os.path.abspath(pid_file)}")
    try:
        config = Config(
            app=UVICORN_CONFIG['app'],
            host=UVICORN_CONFIG['host'],
            port=UVICORN_CONFIG['port'],
            workers=UVICORN_CONFIG.get('workers', 1),
            log_config=UVICORN_CONFIG.get('log_config'),
            log_level=UVICORN_CONFIG.get('log_level', 'info'),
            reload=UVICORN_CONFIG.get('reload', False)
        )
        
        server = Server(config=config)
        server.run()
        
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        cleanup_pid(pid_file)
        sys.exit(1)
    finally:
        cleanup_pid(pid_file)

if __name__ == "__main__":
    start_server()