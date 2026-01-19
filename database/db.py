import sqlite3
import time
from datetime import datetime
from functools import wraps

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_db_path, DB_TIMEOUT, DB_RETRY_ATTEMPTS, DB_RETRY_DELAY


def get_connection():
    """Get a connection to the SQLite database with WAL mode enabled."""
    db_path = get_db_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)

    # Enable WAL mode for better concurrency on network drives
    conn.execute("PRAGMA journal_mode=WAL")
    # Ensure writes are synced to disk
    conn.execute("PRAGMA synchronous=NORMAL")

    return conn


def with_retry(func):
    """Decorator to retry database operations on failure."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(DB_RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                last_error = e
                if attempt < DB_RETRY_ATTEMPTS - 1:
                    time.sleep(DB_RETRY_DELAY)
                    continue
                raise
            except sqlite3.DatabaseError as e:
                last_error = e
                if attempt < DB_RETRY_ATTEMPTS - 1:
                    time.sleep(DB_RETRY_DELAY)
                    continue
                raise
        raise last_error
    return wrapper


@with_retry
def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Approved SKUs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approved_skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Create index for fast SKU lookups and autocomplete
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sku ON approved_skus(sku)
    """)

    conn.commit()
    conn.close()


@with_retry
def create_user(username: str, password_hash: str) -> bool:
    """Create a new user in the database.

    Returns True if successful, False if username already exists.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


@with_retry
def get_user_by_username(username: str) -> dict | None:
    """Get a user by username.

    Returns a dict with user data or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
        (username,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3]
        }
    return None


@with_retry
def get_all_users() -> list[dict]:
    """Get all users from the database.

    Returns a list of user dicts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, created_at FROM users ORDER BY username")
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3]
        }
        for row in rows
    ]


@with_retry
def update_user_password(username: str, new_password_hash: str) -> bool:
    """Update a user's password.

    Returns True if successful, False if user not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (new_password_hash, username)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


@with_retry
def delete_user(username: str) -> bool:
    """Delete a user from the database.

    Returns True if successful, False if user not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


# ==================== SKU Functions ====================

@with_retry
def add_sku(sku: str, description: str = "") -> bool:
    """Add an approved SKU to the database.

    Returns True if successful, False if SKU already exists.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO approved_skus (sku, description, created_at) VALUES (?, ?, ?)",
            (sku.strip().upper(), description.strip(), datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


@with_retry
def add_skus_bulk(skus: list[tuple[str, str]]) -> tuple[int, int]:
    """Add multiple SKUs to the database.

    Args:
        skus: List of (sku, description) tuples

    Returns:
        Tuple of (successful_count, failed_count)
    """
    conn = get_connection()
    cursor = conn.cursor()
    success = 0
    failed = 0
    timestamp = datetime.now().isoformat()

    for sku, description in skus:
        try:
            cursor.execute(
                "INSERT INTO approved_skus (sku, description, created_at) VALUES (?, ?, ?)",
                (sku.strip().upper(), description.strip() if description else "", timestamp)
            )
            success += 1
        except sqlite3.IntegrityError:
            failed += 1

    conn.commit()
    conn.close()
    return success, failed


@with_retry
def delete_sku(sku: str) -> bool:
    """Delete an approved SKU from the database.

    Returns True if successful, False if SKU not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM approved_skus WHERE sku = ?", (sku.upper(),))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


@with_retry
def get_all_skus() -> list[dict]:
    """Get all approved SKUs from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, sku, description, created_at FROM approved_skus ORDER BY sku")
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "sku": row[1],
            "description": row[2],
            "created_at": row[3]
        }
        for row in rows
    ]


@with_retry
def search_skus(prefix: str, limit: int = 10) -> list[dict]:
    """Search for SKUs matching a prefix (for autocomplete).

    Returns up to `limit` matching SKUs.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sku, description FROM approved_skus WHERE sku LIKE ? ORDER BY sku LIMIT ?",
        (prefix.upper() + "%", limit)
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "sku": row[1],
            "description": row[2]
        }
        for row in rows
    ]


@with_retry
def is_valid_sku(sku: str) -> bool:
    """Check if a SKU is in the approved list."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM approved_skus WHERE sku = ?", (sku.strip().upper(),))
    result = cursor.fetchone()
    conn.close()
    return result is not None


@with_retry
def get_sku_count() -> int:
    """Get the total number of approved SKUs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM approved_skus")
    count = cursor.fetchone()[0]
    conn.close()
    return count


@with_retry
def clear_all_skus() -> int:
    """Delete all approved SKUs. Returns the number deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM approved_skus")
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected
