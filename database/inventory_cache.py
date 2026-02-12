"""Local-first inventory cache for fast, stable operations.

This module provides a local SQLite cache that syncs with the remote P: drive
database in the background. All writes go to local first for instant response,
then sync to remote periodically.
"""

import sqlite3
import threading
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_db_path

# ==================== Configuration ====================
INVENTORY_CACHE_SYNC_INTERVAL = 60  # seconds between syncs (reduced frequency to minimize P: drive contention)
INVENTORY_CACHE_ENABLED = True

# ==================== Local Cache State ====================
_sync_thread = None
_sync_stop_event = threading.Event()
_cache_lock = threading.Lock()


def get_local_inventory_path(project: str = "ecoflow") -> Path:
    """Get the local inventory cache path in AppData."""
    if os.name == 'nt':  # Windows
        appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        cache_dir = Path(appdata) / 'The-Uplink'
    else:  # Linux/Mac
        cache_dir = Path.home() / '.local' / 'share' / 'The-Uplink'

    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f'{project}_inventory_cache.db'


def get_remote_inventory_path(project: str = "ecoflow") -> Path:
    """Get the remote inventory database path on P: drive."""
    users_db = get_db_path()
    return users_db.parent / f"{project}_active_inventory.db"


def get_remote_imported_path(project: str = "ecoflow") -> Path:
    """Get the remote imported inventory database path on P: drive."""
    users_db = get_db_path()
    return users_db.parent / f"{project}_imported_inventory.db"


def _get_local_connection(project: str = "ecoflow"):
    """Get connection to local cache database."""
    db_path = get_local_inventory_path(project)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_remote_connection(project: str = "ecoflow"):
    """Get connection to remote database on P: drive."""
    db_path = get_remote_inventory_path(project)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_remote_imported_connection(project: str = "ecoflow"):
    """Get connection to remote imported database on P: drive."""
    db_path = get_remote_imported_path(project)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_local_inventory_cache(project: str = "ecoflow"):
    """Initialize the local inventory cache database."""
    conn = _get_local_connection(project)
    cursor = conn.cursor()

    # Active inventory table (mirrors remote structure + sync tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_sku TEXT NOT NULL,
            serial_number TEXT NOT NULL UNIQUE,
            lpn TEXT NOT NULL,
            location TEXT DEFAULT '',
            repair_state TEXT NOT NULL,
            entered_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            order_number TEXT DEFAULT '',
            sync_status TEXT DEFAULT 'pending',
            remote_id INTEGER DEFAULT NULL,
            last_modified TEXT NOT NULL
        )
    """)

    # Imported/archived inventory table (read-only cache from remote)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imported_inventory (
            id INTEGER PRIMARY KEY,
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

    # Sync metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


def init_inventory_cache():
    """Initialize cache for all projects."""
    for project in ["ecoflow", "halo", "ams_ine"]:
        init_local_inventory_cache(project)


# ==================== Write Operations (Local First) ====================

def add_inventory_item_cached(
    item_sku: str,
    serial_number: str,
    lpn: str,
    repair_state: str,
    entered_by: str,
    location: str = "",
    order_number: str = "",
    project: str = "ecoflow"
) -> bool:
    """Add an inventory item to local cache. Syncs to remote in background."""
    with _cache_lock:
        conn = None
        try:
            conn = _get_local_connection(project)
            cursor = conn.cursor()

            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO inventory
                (item_sku, serial_number, lpn, location, repair_state, entered_by, created_at, order_number, sync_status, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (item_sku, serial_number, lpn, location, repair_state, entered_by, now, order_number, now))

            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception:
            return False
        finally:
            if conn:
                conn.close()


def update_inventory_item_cached(
    item_id: int,
    item_sku: str,
    serial_number: str,
    lpn: str,
    repair_state: str,
    location: str = "",
    order_number: str = "",
    project: str = "ecoflow"
) -> bool:
    """Update an inventory item in local cache."""
    with _cache_lock:
        conn = None
        try:
            conn = _get_local_connection(project)
            cursor = conn.cursor()

            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE inventory
                SET item_sku = ?, serial_number = ?, lpn = ?, location = ?,
                    repair_state = ?, order_number = ?, sync_status = 'pending', last_modified = ?
                WHERE id = ?
            """, (item_sku, serial_number, lpn, location, repair_state, order_number, now, item_id))

            conn.commit()
            return True
        except Exception:
            return False
        finally:
            if conn:
                conn.close()


def delete_inventory_item_cached(item_id: int, project: str = "ecoflow") -> bool:
    """Delete an inventory item from local cache."""
    with _cache_lock:
        conn = None
        try:
            conn = _get_local_connection(project)
            cursor = conn.cursor()

            # Get remote_id before deleting
            cursor.execute("SELECT remote_id FROM inventory WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            remote_id = row[0] if row else None

            # Delete locally
            cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))

            # Track deletion for sync if it was synced
            if remote_id:
                cursor.execute("""
                    INSERT OR REPLACE INTO sync_metadata (key, value)
                    VALUES (?, ?)
                """, (f"delete_{project}_{remote_id}", datetime.now().isoformat()))

            conn.commit()
            return True
        except Exception:
            return False
        finally:
            if conn:
                conn.close()


# ==================== Read Operations (Local Only) ====================

def get_all_inventory_cached(project: str = "ecoflow", limit: int = None, offset: int = 0) -> list[dict]:
    """Get inventory items from local cache (fast)."""
    conn = None
    try:
        conn = _get_local_connection(project)
        cursor = conn.cursor()

        query = """
            SELECT id, item_sku, serial_number, lpn, location, repair_state,
                   entered_by, created_at, order_number, sync_status
            FROM inventory
            ORDER BY created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"

        cursor.execute(query)
        rows = cursor.fetchall()

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
                "order_number": row[8] or '',
                "sync_status": row[9]
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def get_inventory_count_cached(project: str = "ecoflow") -> int:
    """Get total inventory count from local cache."""
    conn = None
    try:
        conn = _get_local_connection(project)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM inventory")
        count = cursor.fetchone()[0]
        return count
    except Exception:
        return 0
    finally:
        if conn:
            conn.close()


def get_all_imported_inventory_cached(project: str = "ecoflow", limit: int = None, offset: int = 0) -> list[dict]:
    """Get imported inventory from local cache."""
    conn = None
    try:
        conn = _get_local_connection(project)
        cursor = conn.cursor()

        query = """
            SELECT id, item_sku, serial_number, lpn, location, repair_state,
                   entered_by, created_at, imported_at, order_number
            FROM imported_inventory
            ORDER BY imported_at DESC, created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"

        cursor.execute(query)
        rows = cursor.fetchall()

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
                "order_number": row[9] or ''
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def get_imported_inventory_count_cached(project: str = "ecoflow") -> int:
    """Get total imported inventory count (real count from remote, stored during sync)."""
    conn = None
    try:
        conn = _get_local_connection(project)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM sync_metadata WHERE key = ?",
            (f"imported_count_{project}",)
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
        return 0
    except Exception:
        return 0
    finally:
        if conn:
            conn.close()


# ==================== Background Sync ====================

def _sync_to_remote(project: str):
    """Sync pending local changes to remote database."""
    local_conn = None
    remote_conn = None
    try:
        local_conn = _get_local_connection(project)
        local_cursor = local_conn.cursor()

        local_cursor.execute("""
            SELECT id, item_sku, serial_number, lpn, location, repair_state,
                   entered_by, created_at, order_number
            FROM inventory
            WHERE sync_status = 'pending'
        """)
        pending_items = local_cursor.fetchall()

        if not pending_items:
            return

        remote_conn = _get_remote_connection(project)
        remote_cursor = remote_conn.cursor()

        for item in pending_items:
            local_id = item[0]
            try:
                remote_cursor.execute("""
                    INSERT OR REPLACE INTO inventory
                    (item_sku, serial_number, lpn, location, repair_state,
                     entered_by, created_at, order_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, item[1:])

                remote_id = remote_cursor.lastrowid

                local_cursor.execute("""
                    UPDATE inventory
                    SET sync_status = 'synced', remote_id = ?
                    WHERE id = ?
                """, (remote_id, local_id))
            except Exception:
                continue

        remote_conn.commit()
        local_conn.commit()
    except Exception:
        pass
    finally:
        if remote_conn:
            try: remote_conn.close()
            except: pass
        if local_conn:
            try: local_conn.close()
            except: pass


def _sync_from_remote(project: str):
    """Pull new items from remote to local cache."""
    local_conn = None
    remote_conn = None
    try:
        local_conn = _get_local_connection(project)
        local_cursor = local_conn.cursor()

        local_cursor.execute("""
            SELECT value FROM sync_metadata WHERE key = ?
        """, (f"last_pull_{project}",))
        row = local_cursor.fetchone()

        remote_conn = _get_remote_connection(project)
        remote_cursor = remote_conn.cursor()

        remote_cursor.execute("""
            SELECT id, item_sku, serial_number, lpn, location, repair_state,
                   entered_by, created_at, order_number
            FROM inventory
            ORDER BY created_at DESC
        """)
        remote_items = remote_cursor.fetchall()

        local_cursor.execute("SELECT serial_number FROM inventory WHERE sync_status = 'synced'")
        local_synced_serials = {row[0] for row in local_cursor.fetchall()}

        remote_serials = set()
        for item in remote_items:
            remote_id, sku, serial, lpn, loc, state, entered, created, order = item
            remote_serials.add(serial)
            if serial not in local_synced_serials:
                try:
                    local_cursor.execute("""
                        INSERT INTO inventory
                        (item_sku, serial_number, lpn, location, repair_state,
                         entered_by, created_at, order_number, sync_status, remote_id, last_modified)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'synced', ?, ?)
                    """, (sku, serial, lpn, loc, state, entered, created, order, remote_id, created))
                except sqlite3.IntegrityError:
                    pass

        # Remove local synced items that no longer exist on remote (e.g., after export)
        stale_serials = local_synced_serials - remote_serials
        if stale_serials:
            placeholders = ','.join('?' * len(stale_serials))
            local_cursor.execute(f"""
                DELETE FROM inventory
                WHERE sync_status = 'synced' AND serial_number IN ({placeholders})
            """, list(stale_serials))

        local_cursor.execute("""
            INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)
        """, (f"last_pull_{project}", datetime.now().isoformat()))

        local_conn.commit()
    except Exception:
        pass
    finally:
        if remote_conn:
            try: remote_conn.close()
            except: pass
        if local_conn:
            try: local_conn.close()
            except: pass


def _sync_imported_from_remote(project: str):
    """Pull imported/archived inventory from remote to local cache."""
    local_conn = None
    remote_conn = None
    try:
        local_conn = _get_local_connection(project)
        local_cursor = local_conn.cursor()

        remote_conn = _get_remote_imported_connection(project)
        remote_cursor = remote_conn.cursor()

        remote_cursor.execute("SELECT COUNT(*) FROM imported_inventory")
        total_count = remote_cursor.fetchone()[0]

        local_cursor.execute("""
            INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)
        """, (f"imported_count_{project}", str(total_count)))

        remote_cursor.execute("""
            SELECT id, item_sku, serial_number, lpn, location, repair_state,
                   entered_by, created_at, imported_at, order_number
            FROM imported_inventory
            ORDER BY imported_at DESC
            LIMIT 100
        """)
        remote_items = remote_cursor.fetchall()

        local_cursor.execute("DELETE FROM imported_inventory")
        for item in remote_items:
            local_cursor.execute("""
                INSERT INTO imported_inventory
                (id, item_sku, serial_number, lpn, location, repair_state,
                 entered_by, created_at, imported_at, order_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, item)

        local_conn.commit()
    except Exception:
        pass
    finally:
        if remote_conn:
            try: remote_conn.close()
            except: pass
        if local_conn:
            try: local_conn.close()
            except: pass


def _background_sync_worker():
    """Background worker that syncs with remote periodically."""
    # Wait before first sync to let the app load without competing for P: drive
    if _sync_stop_event.wait(10):
        return  # Stop was requested during initial delay
    while not _sync_stop_event.is_set():
        for project in ["ecoflow", "halo", "ams_ine"]:
            if _sync_stop_event.is_set():
                return

            try:
                _sync_to_remote(project)
            except Exception:
                pass

            if _sync_stop_event.is_set():
                return

            try:
                _sync_from_remote(project)
            except Exception:
                pass

            if _sync_stop_event.is_set():
                return

            try:
                _sync_imported_from_remote(project)
            except Exception:
                pass

        # Wait for next sync interval (wakes early if stop event is set)
        _sync_stop_event.wait(INVENTORY_CACHE_SYNC_INTERVAL)


def start_inventory_sync():
    """Start the background sync thread."""
    global _sync_thread

    if _sync_thread is not None and _sync_thread.is_alive():
        return

    _sync_stop_event.clear()
    _sync_thread = threading.Thread(target=_background_sync_worker, daemon=True)
    _sync_thread.start()


def stop_inventory_sync():
    """Stop the background sync thread."""
    _sync_stop_event.set()
    if _sync_thread is not None:
        _sync_thread.join(timeout=15)


def force_sync_now():
    """Force an immediate sync (useful for export operations)."""
    for project in ["ecoflow", "halo", "ams_ine"]:
        _sync_to_remote(project)


# ==================== Export Operations ====================

def move_to_imported_cached(project: str = "ecoflow") -> list[dict]:
    """Move all items from active inventory to imported inventory.

    Returns the list of moved items for CSV export.
    """
    local_conn = None
    try:
        local_items = get_all_inventory_cached(project)

        if not local_items:
            return []

        _sync_to_remote(project)

        from .inventory import move_inventory_to_imported
        move_inventory_to_imported(project)

        # ALWAYS clear local active inventory after export
        local_conn = _get_local_connection(project)
        local_cursor = local_conn.cursor()
        local_cursor.execute("DELETE FROM inventory")
        local_conn.commit()

        # Refresh imported cache
        _sync_imported_from_remote(project)

        return local_items
    except Exception:
        return []
    finally:
        if local_conn:
            try: local_conn.close()
            except: pass
