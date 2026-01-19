import sqlite3
import time
from datetime import datetime
from functools import wraps

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_db_path, DB_TIMEOUT, DB_RETRY_ATTEMPTS, DB_RETRY_DELAY


def get_inventory_db_path() -> Path:
    """Get the inventory database path (same directory as users.db)."""
    users_db = get_db_path()
    return users_db.parent / "active_inventory.db"


def get_connection():
    """Get a connection to the inventory database with WAL mode enabled."""
    db_path = get_inventory_db_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)

    # Enable WAL mode for better concurrency on network drives
    conn.execute("PRAGMA journal_mode=WAL")
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
def init_inventory_db():
    """Initialize the inventory database and create the table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_sku TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            lpn TEXT NOT NULL,
            repair_state TEXT NOT NULL,
            entered_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@with_retry
def add_inventory_item(item_sku: str, serial_number: str, lpn: str,
                       repair_state: str, entered_by: str) -> int:
    """Add a new inventory item to the database.

    Returns the ID of the new item.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventory
           (item_sku, serial_number, lpn, repair_state, entered_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item_sku, serial_number, lpn, repair_state, entered_by, datetime.now().isoformat())
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


@with_retry
def get_all_inventory() -> list[dict]:
    """Get all inventory items from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, repair_state, entered_by, created_at
        FROM inventory
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "item_sku": row[1],
            "serial_number": row[2],
            "lpn": row[3],
            "repair_state": row[4],
            "entered_by": row[5],
            "created_at": row[6]
        }
        for row in rows
    ]


@with_retry
def get_inventory_by_user(username: str) -> list[dict]:
    """Get all inventory items entered by a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, repair_state, entered_by, created_at
        FROM inventory
        WHERE entered_by = ?
        ORDER BY created_at DESC
    """, (username,))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "item_sku": row[1],
            "serial_number": row[2],
            "lpn": row[3],
            "repair_state": row[4],
            "entered_by": row[5],
            "created_at": row[6]
        }
        for row in rows
    ]


@with_retry
def update_inventory_item(item_id: int, item_sku: str, serial_number: str,
                          lpn: str, repair_state: str) -> bool:
    """Update an existing inventory item.

    Returns True if successful, False if item not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE inventory
           SET item_sku = ?, serial_number = ?, lpn = ?, repair_state = ?
           WHERE id = ?""",
        (item_sku, serial_number, lpn, repair_state, item_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


@with_retry
def delete_inventory_item(item_id: int) -> bool:
    """Delete an inventory item.

    Returns True if successful, False if item not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0
