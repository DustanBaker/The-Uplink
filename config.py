"""Configuration for The-Uplink application."""

import os
from pathlib import Path

# Application version (update this when releasing new versions)
VERSION = "1.0.3"

# GitHub repository for auto-updates (format: "owner/repo")
# Set to None to disable update checking
GITHUB_REPO = "DustanBaker/The-Uplink"  # TODO: Replace with your GitHub repo

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
_CONFIGURED_DB_PATH = r"P:\Dusty\database\users.db"

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


# ==================== SKU Cache Configuration ====================
# Local caching for approved SKUs to improve performance over VPN

# Enable/disable SKU caching (set to False to use direct database access)
SKU_CACHE_ENABLED = True

# Sync interval in seconds (how often to check remote for updates)
SKU_CACHE_SYNC_INTERVAL = 300  # 5 minutes

# Continue with stale cache if remote sync fails
SKU_CACHE_RETRY_ON_FAIL = True

# Local cache directory (None = auto-detect AppData)
SKU_CACHE_LOCAL_DIR = None


def get_sku_cache_path() -> Path:
    """Get local SKU cache path in AppData (not on network drive).

    Returns:
        Path to local sku_cache.db file
    """
    if SKU_CACHE_LOCAL_DIR:
        cache_dir = Path(SKU_CACHE_LOCAL_DIR)
    elif os.name == 'nt':  # Windows
        appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        cache_dir = Path(appdata) / 'The-Uplink'
    else:  # Linux/Mac
        cache_dir = Path.home() / '.local' / 'share' / 'The-Uplink'

    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / 'sku_cache.db'
