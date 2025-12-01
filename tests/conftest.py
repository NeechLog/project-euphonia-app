import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment variables
def pytest_configure():
    """Configure test environment."""
    # Set test-specific environment variables
    os.environ["TESTING"] = "true"
    
    # Ensure we don't load any real .env files during tests
    if "DOTENV_PATH" not in os.environ:
        os.environ["DOTENV_PATH"] = "/dev/null"

# Add any additional test fixtures here
