#!/usr/bin/env python3
"""
Stop script for the Uvicorn server.
Usage: python3 stop_server.py
"""
import os
import signal
import sys
import time
from pathlib import Path
from api.uvicorn_config import get_pid_file_path

def stop_server():
    """Stop the running Uvicorn server gracefully."""
    pid_file = get_pid_file_path()
    
    if not pid_file.exists():
        print(f"No PID file found at {pid_file.absolute()}. Is the server running?")
        return False
    
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
    except (ValueError, IOError) as e:
        print(f"Error reading PID file: {e}")
        return False
    
    try:
        # Send SIGTERM for graceful shutdown
        os.kill(pid, signal.SIGTERM)
        print(f"Sent shutdown signal to process {pid}...")
        
        # Wait for the process to terminate
        timeout = 10  # seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check if process is still running
                os.kill(pid, 0)
                time.sleep(0.5)
            except (OSError, ProcessLookupError):
                # Process has terminated
                break
        else:
            # If we get here, the process didn't terminate gracefully
            print("Process did not terminate gracefully, forcing shutdown...")
            os.kill(pid, signal.SIGKILL)
        
        # Clean up PID file
        if pid_file.exists():
            pid_file.unlink()
            
        print("Server stopped successfully.")
        return True
        
    except ProcessLookupError:
        print(f"Process {pid} not found. Removing stale PID file.")
        if pid_file.exists():
            pid_file.unlink()
        return False
    except Exception as e:
        print(f"Error stopping server: {e}")
        return False

if __name__ == "__main__":
    stop_server()
