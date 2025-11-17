#!/usr/bin/env python3
"""
Start script for the Uvicorn server.
Usage: python3 start_server.py
"""
import os
import signal
import sys
import uvicorn
import uvicorn.config
from pathlib import Path
from uvicorn.config import Config
from uvicorn import Server
from uvicorn.supervisors import ChangeReload
from uvicorn_config import UVICORN_CONFIG

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
    pid_file = "uvicorn.pid"
    
    # Write PID file first - if this fails, we shouldn't proceed
    if not write_pid(pid_file):
        print("Failed to write PID file. Exiting.", file=sys.stderr)
        sys.exit(1)
        
    # Set up signal handlers after PID file is written
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    print(f"Starting server on {UVICORN_CONFIG['host']}:{UVICORN_CONFIG['port']}")
    print(f"Workers: {UVICORN_CONFIG.get('workers', 1)}")
    
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