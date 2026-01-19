"""Configuration for The-Uplink application."""

import os
from pathlib import Path

# Database path configuration
# Priority: Environment variable > config file > default local path
#
# To use a shared network drive, either:
# 1. Set the environment variable: export UPLINK_DB_PATH="/mnt/shared/uplink/users.db"
# 2. Or edit the DB_PATH below directly

# Default: local database in the database folder
_DEFAULT_DB_PATH = Path(__file__).parent / "database" / "users.db"

# Override path (set this to your shared drive path if not using environment variable)
# Example: "/mnt/shared/uplink/users.db" or "Z:/uplink/users.db" on Windows
_CONFIGURED_DB_PATH = None

def get_db_path() -> Path:
    """Get the database path from environment or config."""
    # Check environment variable first
    env_path = os.environ.get("UPLINK_DB_PATH")
    if env_path:
        return Path(env_path)

    # Check configured path
    if _CONFIGURED_DB_PATH:
        return Path(_CONFIGURED_DB_PATH)

    # Fall back to default
    return _DEFAULT_DB_PATH


# Database connection settings for network reliability
DB_TIMEOUT = 30  # seconds to wait for database lock
DB_RETRY_ATTEMPTS = 3  # number of retries on failure
DB_RETRY_DELAY = 1  # seconds between retries
