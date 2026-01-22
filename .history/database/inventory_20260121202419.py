import sqlite3
import time
from datetime import datetime
from functools import wraps

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_db_path, DB_TIMEOUT, DB_RETRY_ATTEMPTS, DB_RETRY_DELAY


def get_inventory_db_path(project: str = "ecoflow") -> Path:
    """Get the inventory database path (same directory as users.db)."""
    users_db = get_db_path()
    return users_db.parent / f"{project}_active_inventory.db"


def get_connection(project: str = "ecoflow"):
    """Get a connection to the inventory database with WAL mode enabled."""
    db_path = get_inventory_db_path(project)

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
def init_inventory_db(project: str = "ecoflow"):
    """Initialize the inventory database and create the table if it doesn't exist."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_sku TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            lpn TEXT NOT NULL,
            location TEXT DEFAULT '',
            repair_state TEXT NOT NULL,
            entered_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # Add location column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN location TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    conn.commit()
    conn.close()


@with_retry
def add_inventory_item(item_sku: str, serial_number: str, lpn: str,
                       location: str, repair_state: str, entered_by: str,
                       project: str = "ecoflow") -> int:
    """Add a new inventory item to the database.

    Returns the ID of the new item.
    """
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventory
           (item_sku, serial_number, lpn, location, repair_state, entered_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (item_sku, serial_number, lpn, location, repair_state, entered_by, datetime.now().isoformat())
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


@with_retry
def get_all_inventory(project: str = "ecoflow") -> list[dict]:
    """Get all inventory items from the database."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at
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
            "location": row[4] or '',
            "repair_state": row[5],
            "entered_by": row[6],
            "created_at": row[7]
        }
        for row in rows
    ]


@with_retry
def get_inventory_by_user(username: str, project: str = "ecoflow") -> list[dict]:
    """Get all inventory items entered by a specific user."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at
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
            "location": row[4] or '',
            "repair_state": row[5],
            "entered_by": row[6],
            "created_at": row[7]
        }
        for row in rows
    ]


@with_retry
def update_inventory_item(item_id: int, item_sku: str, serial_number: str,
                          lpn: str, location: str, repair_state: str,
                          project: str = "ecoflow") -> bool:
    """Update an existing inventory item.

    Returns True if successful, False if item not found.
    """
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE inventory
           SET item_sku = ?, serial_number = ?, lpn = ?, location = ?, repair_state = ?
           WHERE id = ?""",
        (item_sku, serial_number, lpn, location, repair_state, item_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


@with_retry
def delete_inventory_item(item_id: int, project: str = "ecoflow") -> bool:
    """Delete an inventory item.

    Returns True if successful, False if item not found.
    """
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def get_imported_inventory_db_path(project: str = "ecoflow") -> Path:
    """Get the imported inventory database path."""
    users_db = get_db_path()
    return users_db.parent / f"{project}_imported_inventory.db"


def get_imported_connection(project: str = "ecoflow"):
    """Get a connection to the imported inventory database."""
    db_path = get_imported_inventory_db_path(project)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@with_retry
def init_imported_inventory_db(project: str = "ecoflow"):
    """Initialize the imported inventory database."""
    conn = get_imported_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imported_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_sku TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            lpn TEXT NOT NULL,
            location TEXT DEFAULT '',
            repair_state TEXT NOT NULL,
            entered_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
    """)
    # Add location column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE imported_inventory ADD COLUMN location TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    conn.commit()
    conn.close()


@with_retry
def move_inventory_to_imported(project: str = "ecoflow") -> list[dict]:
    """Move all items from active inventory to imported inventory.

    Returns the list of moved items for CSV export.
    """
    # Initialize imported db if needed
    init_imported_inventory_db(project)

    # Get all active inventory items
    items = get_all_inventory(project)

    if not items:
        return []

    # Insert into imported inventory
    imported_conn = get_imported_connection(project)
    imported_cursor = imported_conn.cursor()
    imported_at = datetime.now().isoformat()

    for item in items:
        imported_cursor.execute(
            """INSERT INTO imported_inventory
               (item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (item['item_sku'], item['serial_number'], item['lpn'], item.get('location', ''),
             item['repair_state'], item['entered_by'], item['created_at'], imported_at)
        )

    imported_conn.commit()
    imported_conn.close()

    # Clear active inventory
    active_conn = get_connection(project)
    active_cursor = active_conn.cursor()
    active_cursor.execute("DELETE FROM inventory")
    active_conn.commit()
    active_conn.close()

    return items


@with_retry
def get_all_imported_inventory(project: str = "ecoflow") -> list[dict]:
    """Get all items from the imported inventory database."""
    init_imported_inventory_db(project)

    conn = get_imported_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, imported_at
        FROM imported_inventory
        ORDER BY imported_at DESC, created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "item_sku": row[1],
            "serial_number": row[2],
            "lpn": row[3],
            "location": row[4] or '',
            "repair_state": row[5],
            "entered_by": row[6],
            "created_at": row[7],
            "imported_at": row[8]
        }
        for row in rows
    ]


def export_inventory_to_csv(items: list[dict], filepath: str, project: str = "ecoflow") -> bool:
    """Export inventory items to CSV with project-specific format.

    Returns True if successful.
    """
    import csv

    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            if project == "halo":
                # Halo format - 16 columns
                writer.writerow(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16'])
                writer.writerow(['SN', 'LPN', 'Location', 'Client', 'PONo', 'Client Order', 'SKU', 'Asset', 'RecDate', 'Qty', 'Qty Free', 'WO #', 'Repair State', 'Grade', 'Shippable', 'RMA #'])

                for item in items:
                    created = item['created_at']
                    i
                    f 'T' in created:
                        rec_date = created.replace('T', ' ').split('.')[0]
                    else:
                        rec_date = created[:19]

                    writer.writerow([
                        item['serial_number'],      # SN
                        item['lpn'],                # LPN
                        item.get('location', ''),   # Location
                        '57',                         # Client
                        '',                         # PONo
                        '',                         # Client Order
                        item['item_sku'],           # SKU
                        '',                         # Asset
                        rec_date,                   # RecDate
                        '1',                        # Qty
                        '1',                        # Qty Free
                        '',                         # WO #
                        item['repair_state'],       # Repair State
                        '',                         # Grade
                        '',                         # Shippable
                        ''                          # RMA #
                    ])
            else:
                # EcoFlow format - 18 columns
                writer.writerow(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18'])
                writer.writerow(['SN', 'LPN', 'Location', 'Client', 'PO #', 'Order #', 'Item', 'Rec Date', 'Qty', 'Qty Free', 'Shippable', 'Repair State', 'Firmware', 'Program', 'Warranty', 'Consigned', 'PartType', 'Grade'])

                for item in items:
                    created = item['created_at']
                    if 'T' in created:
                        rec_date = created.replace('T', ' ').split('.')[0]
                    else:
                        rec_date = created[:19]

                    writer.writerow([
                        item['serial_number'],      # SN
                        item['lpn'],                # LPN
                        item.get('location', ''),   # Location
                        '82',                         # Client
                        '',                         # PO #
                        '',                         # Order #
                        item['item_sku'],           # Item
                        rec_date,                   # Rec Date
                        '1',                        # Qty
                        '1',                        # Qty Free
                        '',                         # Shippable
                        item['repair_state'],       # Repair State
                        '',                         # Firmware
                        '',                         # Program
                        '',                         # Warranty
                        '',                         # Consigned
                        '',                         # PartType
                        ''                          # Grade
                    ])

        return True
    except Exception:
        return False
