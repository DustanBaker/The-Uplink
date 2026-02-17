import sqlite3
import time
import threading
from datetime import datetime
from functools import wraps

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_db_path, DB_TIMEOUT, DB_RETRY_ATTEMPTS, DB_RETRY_DELAY

# ==================== Halo SN Lookup Cache ====================
# In-memory cache for Halo PO number lookups to reduce network traffic
_halo_sn_cache = {}  # {serial_number: po_number}
_halo_sn_cache_loaded = False
_halo_sn_cache_lock = threading.Lock()


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
            created_at TEXT NOT NULL,
            order_number TEXT DEFAULT ''
        )
    """)
    # Add location column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN location TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    # Add order_number column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN order_number TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    # Add tracking_number column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE inventory ADD COLUMN tracking_number TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    conn.commit()
    conn.close()


@with_retry
def add_inventory_item(item_sku: str, serial_number: str, lpn: str,
                       location: str, repair_state: str, entered_by: str,
                       project: str = "ecoflow", order_number: str = "",
                       tracking_number: str = "") -> int:
    """Add a new inventory item to the database.

    Returns the ID of the new item.
    """
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventory
           (item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, order_number, tracking_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_sku, serial_number, lpn, location, repair_state, entered_by, datetime.now().isoformat(), order_number, tracking_number)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


@with_retry
def get_all_inventory(project: str = "ecoflow", limit: int = None) -> list[dict]:
    """Get all inventory items from the database.

    Args:
        project: The project name (ecoflow or halo)
        limit: Optional limit on number of records to return (for performance)
    """
    conn = get_connection(project)
    cursor = conn.cursor()

    query = """
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, order_number, tracking_number
        FROM inventory
        ORDER BY created_at DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
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
            "order_number": row[8] or '' if len(row) > 8 else '',
            "tracking_number": row[9] or '' if len(row) > 9 else ''
        }
        for row in rows
    ]


@with_retry
def get_inventory_count(project: str = "ecoflow") -> int:
    """Get total count of active inventory items."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM inventory")
    count = cursor.fetchone()[0]
    conn.close()
    return count


@with_retry
def get_imported_inventory_count(project: str = "ecoflow") -> int:
    """Get total count of archived/imported inventory items."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM imported_inventory")
    count = cursor.fetchone()[0]
    conn.close()
    return count


@with_retry
def get_inventory_by_user(username: str, project: str = "ecoflow") -> list[dict]:
    """Get all inventory items entered by a specific user."""
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, order_number
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
            "created_at": row[7],
            "order_number": row[8] or '' if len(row) > 8 else ''
        }
        for row in rows
    ]


@with_retry
def update_inventory_item(item_id: int, item_sku: str, serial_number: str,
                          lpn: str, location: str, repair_state: str,
                          project: str = "ecoflow", order_number: str = "",
                          tracking_number: str = "") -> bool:
    """Update an existing inventory item.

    Returns True if successful, False if item not found.
    """
    conn = get_connection(project)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE inventory
           SET item_sku = ?, serial_number = ?, lpn = ?, location = ?, repair_state = ?, order_number = ?, tracking_number = ?
           WHERE id = ?""",
        (item_sku, serial_number, lpn, location, repair_state, order_number, tracking_number, item_id)
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
            imported_at TEXT NOT NULL,
            order_number TEXT DEFAULT ''
        )
    """)
    # Add location column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE imported_inventory ADD COLUMN location TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    # Add order_number column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE imported_inventory ADD COLUMN order_number TEXT DEFAULT ''")
    except:
        pass  # Column already exists
    # Add tracking_number column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE imported_inventory ADD COLUMN tracking_number TEXT DEFAULT ''")
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
               (item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, imported_at, order_number, tracking_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item['item_sku'], item['serial_number'], item['lpn'], item.get('location', ''),
             item['repair_state'], item['entered_by'], item['created_at'], imported_at, item.get('order_number', ''), item.get('tracking_number', ''))
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
def get_all_imported_inventory(project: str = "ecoflow", limit: int = None) -> list[dict]:
    """Get all items from the imported inventory database.

    Args:
        project: The project name (ecoflow or halo)
        limit: Optional limit on number of records to return (for performance)
    """
    init_imported_inventory_db(project)

    conn = get_imported_connection(project)
    cursor = conn.cursor()

    query = """
        SELECT id, item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, imported_at, order_number, tracking_number
        FROM imported_inventory
        ORDER BY imported_at DESC, created_at DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
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
            "imported_at": row[8],
            "order_number": row[9] or '' if len(row) > 9 else '',
            "tracking_number": row[10] or '' if len(row) > 10 else ''
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
                    if 'T' in created:
                        rec_date = created.replace('T', ' ').split('.')[0]
                    else:
                        rec_date = created[:19]

                    # Look up PO # from SN lookup table
                    po_number = lookup_halo_po_number(item['serial_number']) or '0'

                    writer.writerow([
                        item['serial_number'] or '0',           # SN
                        item['lpn'] or '0',                     # LPN
                        item.get('location') or '0',            # Location
                        '57',                                   # Client
                        po_number,                              # PONo (from SN lookup)
                        '0',                                    # Client Order
                        item['item_sku'] or '0',                # SKU
                        '0',                                    # Asset
                        rec_date or '0',                        # RecDate
                        '1',                                    # Qty
                        '1',                                    # Qty Free
                        '0',                                    # WO #
                        item['repair_state'] or '0',            # Repair State
                        '0',                                    # Grade
                        '0',                                    # Shippable
                        '0'                                     # RMA #
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
                        item['serial_number'] or '0',           # SN
                        item['lpn'] or '0',                     # LPN
                        item.get('location') or '0',            # Location
                        '82',                                   # Client
                        item.get('tracking_number') or '0',     # PO #
                        item.get('order_number') or '0',        # Order #
                        item['item_sku'] or '0',                # Item
                        rec_date or '0',                        # Rec Date
                        '1',                                    # Qty
                        '1',                                    # Qty Free
                        '0',                                    # Shippable
                        item['repair_state'] or '0',            # Repair State
                        '0',                                    # Firmware
                        '0',                                    # Program
                        '0',                                    # Warranty
                        '0',                                    # Consigned
                        '0',                                    # PartType
                        '0'                                     # Grade
                    ])

        return True
    except Exception:
        return False


# ==================== Halo SN Lookup Functions ====================

def get_halo_sn_lookup_db_path() -> Path:
    """Get the Halo SN lookup database path."""
    users_db = get_db_path()
    return users_db.parent / "halo_sn_lookup.db"


def get_sn_lookup_connection():
    """Get a connection to the Halo SN lookup database."""
    db_path = get_halo_sn_lookup_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@with_retry
def init_halo_sn_lookup_db():
    """Initialize the Halo SN lookup database."""
    conn = get_sn_lookup_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sn_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number TEXT NOT NULL UNIQUE,
            po_number TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sn_lookup_serial ON sn_lookup(serial_number)")
    conn.commit()
    conn.close()


@with_retry
def import_halo_sn_lookup_csv(csv_path: str) -> int:
    """Import Halo SN lookup data from CSV file.

    Returns the number of records imported.
    """
    import csv

    init_halo_sn_lookup_db()

    conn = get_sn_lookup_connection()
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM sn_lookup")

    count = 0
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        # Skip header row
        next(reader, None)

        for row in reader:
            if len(row) >= 2 and row[0].strip():
                serial_number = row[0].strip()
                po_number = row[1].strip() if row[1].strip() else ''
                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO sn_lookup (serial_number, po_number) VALUES (?, ?)",
                        (serial_number, po_number)
                    )
                    count += 1
                except:
                    pass  # Skip invalid rows

    conn.commit()
    conn.close()

    # Refresh the in-memory cache after import
    refresh_halo_sn_cache()

    return count


def _load_halo_sn_cache():
    """Load all Halo SN lookups into memory cache (called once at startup)."""
    global _halo_sn_cache, _halo_sn_cache_loaded

    with _halo_sn_cache_lock:
        if _halo_sn_cache_loaded:
            return

        try:
            init_halo_sn_lookup_db()
            conn = get_sn_lookup_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT serial_number, po_number FROM sn_lookup")
            rows = cursor.fetchall()
            conn.close()

            _halo_sn_cache = {row[0]: row[1] for row in rows}
            _halo_sn_cache_loaded = True
        except Exception:
            pass  # Cache remains empty, will fall back to direct lookup


def refresh_halo_sn_cache():
    """Force refresh of the Halo SN cache from database."""
    global _halo_sn_cache_loaded
    with _halo_sn_cache_lock:
        _halo_sn_cache_loaded = False
    _load_halo_sn_cache()


def lookup_halo_po_number(serial_number: str, blocking: bool = True) -> str:
    """Look up PO number for a Halo serial number.

    Uses in-memory cache to avoid network calls.
    Returns the PO number if found, empty string otherwise.

    Args:
        serial_number: The serial number to look up.
        blocking: If True, blocks until cache is loaded from P: drive.
                  If False, returns '' immediately if cache isn't ready yet.
    """
    # Load cache if not loaded
    if not _halo_sn_cache_loaded:
        if blocking:
            _load_halo_sn_cache()
        else:
            return ''  # Cache not ready, return empty to avoid blocking

    # Use cache lookup (instant, no network)
    with _halo_sn_cache_lock:
        return _halo_sn_cache.get(serial_number, '')


@with_retry
def get_halo_sn_lookup_count() -> int:
    """Get the number of records in the Halo SN lookup table."""
    # Use cache if available
    if _halo_sn_cache_loaded:
        with _halo_sn_cache_lock:
            return len(_halo_sn_cache)

    init_halo_sn_lookup_db()
    conn = get_sn_lookup_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sn_lookup")
    count = cursor.fetchone()[0]
    conn.close()
    return count
