"""
Access Database backend for lookup operations.
Optimized for SQL-based matching and aggregations.
"""

import os
import csv
import shutil
import getpass
from datetime import datetime
import pandas as pd
import pyodbc
from openpyxl.utils import get_column_letter

# ==========================================
# CONFIGURATION
# ==========================================
KEYWORD_Y = "Take"
FORMAT_SHIFT_DATE = datetime(2024, 3, 15)
DB_FILENAME = "lookup.accdb"
CONNECTION_STRING = None  # Set dynamically

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
def _get_db_path(lookup_dir=None):
    """Get the Access database path."""
    if lookup_dir is None:
        lookup_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(lookup_dir, DB_FILENAME)


def _get_connection_string(db_path):
    """Build ODBC connection string for Access database."""
    return (
        f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};"
        f"DBQ={db_path};"
        f"Pwd=;"
    )


def _init_database(db_path):
    """Create Access database and tables if they don't exist."""
    if not os.path.exists(db_path):
        import subprocess
        # Create empty Access database using COM or command line
        try:
            import win32com.client
            access = win32com.client.Dispatch("Access.Application")
            access.NewCurrentDatabase(db_path)
            access.Quit()
        except Exception:
            # Fallback: create via ODBC (requires driver)
            conn_str = _get_connection_string(db_path)
            try:
                pyodbc.connect(conn_str).close()
            except Exception as e:
                raise RuntimeError(
                    f"Could not create Access database at {db_path}. "
                    "Ensure Microsoft Access Driver is installed. Error: {e}"
                )

    conn = pyodbc.connect(_get_connection_string(db_path))
    cursor = conn.cursor()

    # Create paths_registry table
    try:
        cursor.execute("""
            CREATE TABLE paths_registry (
                id AUTOINCREMENT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                engine TEXT,
                date_tested DATETIME,
                date_added DATETIME DEFAULT NOW(),
                added_by TEXT,
                created_at DATETIME DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception:
        pass  # Table may already exist

    # Create master_data table
    try:
        cursor.execute("""
            CREATE TABLE master_data (
                id AUTOINCREMENT PRIMARY KEY,
                engine TEXT,
                date_tested DATETIME UNIQUE,
                perf_point TEXT,
                created_at DATETIME DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception:
        pass

    # Create parameters table
    try:
        cursor.execute("""
            CREATE TABLE parameters (
                id AUTOINCREMENT PRIMARY KEY,
                param_name TEXT NOT NULL UNIQUE,
                param_value TEXT,
                is_formula BIT DEFAULT 0,
                created_at DATETIME DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception:
        pass

    # Create parameter_values table (normalized for efficient storage)
    try:
        cursor.execute("""
            CREATE TABLE parameter_values (
                id AUTOINCREMENT PRIMARY KEY,
                master_data_id INTEGER,
                param_name TEXT,
                value TEXT,
                FOREIGN KEY (master_data_id) REFERENCES master_data(id)
            )
        """)
        conn.commit()
    except Exception:
        pass

    cursor.close()
    conn.close()


def get_connection(db_path=None):
    """Get a connection to the Access database."""
    if db_path is None:
        db_path = _get_db_path()
    _init_database(db_path)
    return pyodbc.connect(_get_connection_string(db_path))


# ==========================================
# PATHS REGISTRY OPERATIONS
# ==========================================
def add_path_registry_entry(new_path, db_path=None, added_by=None, engine_name=None):
    """Add a new path to the registry with metadata."""
    normalized_path = str(new_path or "").strip()
    if not normalized_path:
        return {"ok": False, "message": "Path is empty."}

    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # Check if path already exists
        cursor.execute("SELECT id FROM paths_registry WHERE LOWER(path) = ?", (normalized_path.lower(),))
        if cursor.fetchone():
            conn.close()
            return {"ok": False, "message": "Path already exists in registry."}

        # Extract date_tested from file
        from loopup import _extract_latest_test_date
        date_tested = _extract_latest_test_date(normalized_path)

        # Prepare insert
        user = added_by or _get_windows_user()
        engine = str(engine_name or "").strip()

        cursor.execute("""
            INSERT INTO paths_registry (path, engine, date_tested, date_added, added_by)
            VALUES (?, ?, ?, ?, ?)
        """, (normalized_path, engine, date_tested or None, datetime.now(), user))

        conn.commit()
        conn.close()

        return {
            "ok": True,
            "message": "Path added.",
            "record": {
                "Path": normalized_path,
                "Engine": engine,
                "Date_Tested": date_tested,
                "Date_Added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Added_By": user,
            },
        }
    except Exception as e:
        conn.close()
        return {"ok": False, "message": f"Error adding path: {e}"}


def get_latest_paths(limit=100, db_path=None):
    """Get latest registry entries as records, sorted by date_added descending."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = """
        SELECT path, engine, date_tested, date_added, added_by
        FROM paths_registry
        ORDER BY date_added DESC
    """

    if limit and limit > 0:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "Path": row[0],
            "Engine": row[1] or "",
            "Date_Tested": str(row[2]) if row[2] else "",
            "Date_Added": str(row[3]) if row[3] else "",
            "Added_By": row[4] or "",
        }
        for row in rows
    ]


# ==========================================
# MASTER DATA OPERATIONS
# ==========================================
def ingest_master_data(date_tested, engine, perf_point, param_values, db_path=None):
    """
    Insert a row of master data with normalized parameter values.
    date_tested is UNIQUE - duplicates are skipped silently.
    """
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # Check if date_tested already exists
        normalized_date = _normalize_date_key(date_tested)
        cursor.execute("SELECT id FROM master_data WHERE date_tested = ?", (normalized_date,))
        if cursor.fetchone():
            conn.close()
            return {"ok": False, "message": "Duplicate date_tested; skipped.", "skipped": True}

        # Insert master_data row
        cursor.execute("""
            INSERT INTO master_data (engine, date_tested, perf_point)
            VALUES (?, ?, ?)
        """, (engine, normalized_date, perf_point))
        conn.commit()

        master_data_id = cursor.lastrowid

        # Insert parameter values
        for param_name, param_val in param_values.items():
            cursor.execute("""
                INSERT INTO parameter_values (master_data_id, param_name, value)
                VALUES (?, ?, ?)
            """, (master_data_id, param_name, param_val))

        conn.commit()
        conn.close()
        return {"ok": True, "message": "Row inserted.", "id": master_data_id}
    except Exception as e:
        conn.close()
        return {"ok": False, "message": f"Error inserting data: {e}"}


def get_master_data_by_date(date_tested, db_path=None):
    """Retrieve master data row by date_tested."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    normalized_date = _normalize_date_key(date_tested)
    cursor.execute("SELECT id, engine, perf_point FROM master_data WHERE date_tested = ?", (normalized_date,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    master_id, engine, perf = row

    # Fetch all parameter values for this row
    cursor.execute("""
        SELECT param_name, value FROM parameter_values WHERE master_data_id = ?
    """, (master_id,))

    params = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    return {"id": master_id, "engine": engine, "perf_point": perf, "params": params}


def clear_master_data(db_path=None):
    """Clear all master data (for rescan)."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM parameter_values")
        cursor.execute("DELETE FROM master_data")
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Master data cleared."}
    except Exception as e:
        conn.close()
        return {"ok": False, "message": f"Error clearing data: {e}"}


# ==========================================
# PARAMETERS OPERATIONS
# ==========================================
def add_parameter(param_name, param_value=None, is_formula=False, db_path=None):
    """Add a parameter to the parameters table."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO parameters (param_name, param_value, is_formula) VALUES (?, ?, ?)",
            (param_name, param_value, 1 if is_formula else 0),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "message": f"Parameter '{param_name}' added."}
    except Exception as e:
        conn.close()
        return {"ok": False, "message": f"Error adding parameter: {e}"}


def get_all_parameters(db_path=None):
    """Get all parameters from the database."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT param_name FROM parameters ORDER BY param_name")
    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def _get_windows_user():
    """Best-effort resolution of the active Windows username."""
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or getpass.getuser()
        or "unknown"
    )


def _normalize_date_key(value):
    """Normalize date for SQL storage and matching."""
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "none"}:
        return None

    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    return raw
