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
env_path = Path(__file__).parent / '.env'
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

def start_server(background=True):
    """Start the Uvicorn server with the specified configuration.
    
    Args:
        background (bool): If True, run the server in the background. Defaults to True.
    """
    pid_file = get_pid_file_path()
    try:
        # Get config directory from environment or use None for default
        config_dir = os.environ.get('AUTH_CONFIG_DIR')
        if config_dir:
            print(f"Using auth config from: {config_dir}")
            init_auth_config(config_dir=Path(config_dir))
        else:
            init_auth_config()
        print("AuthConfig initialized successfully")
    except Exception as e:
        print(f"Error initializing AuthConfig: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Set up signal handlers
    # signal.signal(signal.SIGINT, handle_exit)
    # signal.signal(signal.SIGTERM, handle_exit)
    
    if background:
        import subprocess
        import atexit
        
        # Prepare the command to run uvicorn
        cmd = [
            'uvicorn',
            f'{UVICORN_CONFIG["app"]}:app',
            f'--host={UVICORN_CONFIG["host"]}',
            f'--port={UVICORN_CONFIG["port"]}',
            f'--workers={UVICORN_CONFIG.get("workers", 1)}',
            f'--log-level={UVICORN_CONFIG.get("log_level", "info")}'
        ]
        
        if UVICORN_CONFIG.get('reload', False):
            cmd.append('--reload')
        
        # Start the process in the background
        try:
            # Create log directory if it doesn't exist
            log_dir = Path('logs')
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / 'uvicorn.log'
            
            # Start process with no terminal attachment and redirect output
            with open(log_file, 'a') as log_handle:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True
                )
            
            # Write the child process ID to the PID file
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            print(f"✅ Server started in background with PID: {process.pid}")
            print(f"🌐 Access URL: http://{UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
            print(f"👥 Workers: {UVICORN_CONFIG.get('workers', 1)}")
            print(f"📄 PID file: {os.path.abspath(pid_file)}")
            print(f"📝 Logs: {log_file.absolute()}")
            print("\nTo stop the server, run:")
            print(f"  kill {process.pid}  # or use the stop_server.py script")
            process.add_signal_handler(signal.SIGINT, handle_exit)
            process.add_signal_handler(signal.SIGTERM, handle_exit)
            # Note: We don't register an atexit handler here because:
            # 1. The server is running in the background
            # 2. We want the PID file to persist after this process exits
            # 3. The stop_server.py script will handle cleanup when stopping the server
            return
                
        except Exception as e:
            print(f"❌ Error starting server: {e}", file=sys.stderr)
            cleanup_pid(pid_file)
            sys.exit(1)
            
    else:
        # Original blocking implementation
        if not write_pid(pid_file):
            print("Failed to write PID file. Exiting.", file=sys.stderr)
            sys.exit(1)
            
        pid = os.getpid()
        print(f"Starting server in foreground on {UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
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
            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)
            atexit.register(cleanup_pid, pid_file)
            server = Server(config=config)
            server.run()
            
            
        except Exception as e:
            print(f"Error starting server: {e}", file=sys.stderr)
            cleanup_pid(pid_file)
            sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Start the Uvicorn server')
    parser.add_argument('--foreground', '-f', action='store_true',
                      help='Run the server in the foreground (blocking)')
    args = parser.parse_args()
    
    start_server(background=not args.foreground)