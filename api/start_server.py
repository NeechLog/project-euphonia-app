#!/usr/bin/env python3
"""
Start script for the Uvicorn server.
Usage: python3 start_server.py
"""
import os
import sys
import signal
import atexit
import logging
import uvicorn
import daemon
import daemon.pidfile
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

def check_existing_server(pid_file: str) -> tuple[bool, str | None]:
    """
    Check if a server is already running by checking the PID file.

    Args:
        pid_file: Path to the PID file to check

    Returns:
        tuple: (is_running: bool, pid: str | None)
            - is_running: True if a server appears to be running
            - pid: The PID if a server is running, None otherwise
    """
    try:
        if not os.path.exists(pid_file):
            return False, None

        with open(pid_file, 'r') as f:
            pid = f.read().strip()

        if not pid:
            return False, None

        # Check if process is still running
        try:
            # Try Linux /proc method first
            if os.path.exists(f'/proc/{pid}'):
                return True, pid
        except (ValueError, PermissionError):
            pass

        # Fallback method using psutil if available
        try:
            import psutil
            if psutil.pid_exists(int(pid)):
                return True, pid
        except (ImportError, ValueError):
            pass

        # If we get here, the PID file exists but process isn't running
        return False, pid

    except (IOError, OSError) as e:
        print(f"⚠️  Warning: Could not check PID file {pid_file}: {e}", file=sys.stderr)
        return False, None

def run_uvicorn():
    """Run the Uvicorn server with the specified configuration."""
    try:
        # Initialize auth config
        config_dir = os.environ.get('AUTH_CONFIG_DIR')
        if config_dir:
            print(f"Using auth config from: {config_dir}")
            init_auth_config(base_dir=Path(config_dir))
        else:
            init_auth_config()
        print("AuthConfig initialized successfully")
        
        # Set up logging
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / 'uvicorn.log'
        
        # Configure Uvicorn
        config = Config(
            app=UVICORN_CONFIG['app'],
            host=UVICORN_CONFIG['host'],
            port=UVICORN_CONFIG['port'],
            workers=UVICORN_CONFIG.get('workers', 1),
            log_config=UVICORN_CONFIG.get('log_config'),
            log_level=UVICORN_CONFIG.get('log_level', 'info'),
            reload=UVICORN_CONFIG.get('reload', False)
        )
        
        # Set up logging to file
        logging.basicConfig(
            filename=log_file,
            level=getattr(logging, UVICORN_CONFIG.get('log_level', 'info').upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create and run the server
        server = Server(config=config)
        server.run()
        
    except Exception as e:
        logging.error(f"Error in Uvicorn server: {e}", exc_info=True)
        raise

def start_server(background=True):
    """Start the Uvicorn server with the specified configuration.
    
    Args:
        background (bool): If True, run the server in the background. Defaults to True.
    """
    pid_file = get_pid_file_path()
    
    # Check for existing server
    is_running, pid = check_existing_server(pid_file)
    if is_running:
        print(f"❌ Server is already running with PID {pid}")
        print(f"   If this is incorrect, remove the PID file: {pid_file}")
        sys.exit(1)
    elif pid:  # Stale PID file
        print(f"ℹ️  Found stale PID file for process {pid}, removing...")
        cleanup_pid(pid_file)
    
    if background:
        print("🚀 Starting server in background...")
        
        # Set up working directory
        working_dir = str(Path(__file__).parent.absolute())
        
        # Set up log files
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        stdout_log = str(log_dir / 'uvicorn_stdout.log')
        stderr_log = str(log_dir / 'uvicorn_stderr.log')
        
        # Open file handles for logging
        stdout_fd = open(stdout_log, 'a+')
        stderr_fd = open(stderr_log, 'a+')
        
        # Set up PID file handler
        pidfile = daemon.pidfile.PIDLockFile(pid_file)
        
        # Set up context
        context = daemon.DaemonContext(
            working_directory=working_dir,
            umask=0o002,
            pidfile=pidfile,
            stdout=stdout_fd,
            stderr=stderr_fd,
            detach_process=True,
            prevent_core=True,
            signal_map={
                signal.SIGTERM: handle_exit,
                signal.SIGINT: handle_exit,
                signal.SIGTSTP: handle_exit,
            },
            files_preserve=[
                stdout_fd,
                stderr_fd,
            ]
        )
        
        # Start the daemon
        with context:
            # The PID file is automatically managed by PIDLockFile
            # Run the server
            run_uvicorn()
        
        print(f"✅ Server started in background with PID: {os.getpid()}")
        print(f"🌐 Access URL: http://{UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
        print(f"👥 Workers: {UVICORN_CONFIG.get('workers', 1)}")
        print(f"📄 PID file: {os.path.abspath(pid_file)}")
        print(f"📝 Logs: {os.path.abspath(log_dir)}/uvicorn_*.log")
        print("\nTo stop the server, run:")
        print(f"  kill $(cat {pid_file})  # or use the stop_server.py script")
    
    else:
        # Run in foreground
        print(f"🚀 Starting server in foreground on {UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
        print(f"👥 Workers: {UVICORN_CONFIG.get('workers', 1)}")
        print(f"Process ID: {os.getpid()} | PID file: {os.path.abspath(pid_file)}")
        
        try:
            if not write_pid(pid_file):
                print("Failed to write PID file. Exiting.", file=sys.stderr)
                sys.exit(1)
                
            # Set up signal handlers
            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)
            atexit.register(cleanup_pid, pid_file)
            
            # Run the server
            run_uvicorn()
            
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