"""
Access Database backend for lookup operations.
Stores one wide database row per matched run column and fetches only the
requested parameter columns for graphing.
"""

import getpass
import os
import re
from datetime import datetime

import pandas as pd
import pyodbc

from lookup.loopup import (
    _extract_latest_test_date,
    _fallback_engine_name,
    _normalize_date_key,
    iter_lookup_columns,
    preview_run_file,
)


DB_FILENAME = "lookup.accdb"
MASTER_TABLE = "master_data"
PARAMETERS_TABLE = "parameters"
PATHS_TABLE = "paths_registry"
DISPLAY_BASE_COLUMNS = {
    "Engine": "engine",
    "Date_Tested": "date_tested",
    "Perf. Point": "perf_point",
    "Path": "source_path",
    "Filename": "source_file",
    "Parent_Folder": "parent_folder",
}
NON_NUMERIC_COLUMNS = {
    "Engine",
    "Date_Tested",
    "Perf. Point",
    "Path",
    "Filename",
    "Parent_Folder",
}


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


def _quote_identifier(name):
    """Safely quote Access identifiers."""
    return f"[{str(name).replace(']', ']]')}]"


def _get_windows_user():
    """Best-effort resolution of the active Windows username."""
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or getpass.getuser()
        or "unknown"
    )


def _build_lookup_key(source_path, date_key, perf_point):
    """Stable row identity for one matched test column in one source file."""
    normalized_path = os.path.normcase(os.path.normpath(str(source_path or "").strip()))
    normalized_perf = str(perf_point or "").strip()
    normalized_date = str(date_key or "").strip()
    return "|".join([normalized_path, normalized_date, normalized_perf])


def _sanitize_column_name(param_name):
    """Convert a parameter label into a safe Access column identifier."""
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", str(param_name or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "param"
    if cleaned[0].isdigit():
        cleaned = f"p_{cleaned}"
    return cleaned[:48]


def _normalize_db_value(value):
    """Store values as compact strings so mixed parameter types stay importable."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float) and pd.isna(value):
        return None
    return str(value)


def _create_database_file(db_path):
    """Create an empty Access file when it does not exist yet."""
    if os.path.exists(db_path):
        return

    try:
        import win32com.client

        access = win32com.client.Dispatch("Access.Application")
        access.NewCurrentDatabase(db_path)
        access.Quit()
        return
    except Exception:
        pass

    conn_str = _get_connection_string(db_path)
    try:
        pyodbc.connect(conn_str).close()
    except Exception as exc:
        raise RuntimeError(
            f"Could not create Access database at {db_path}. Ensure the Access driver is installed. Error: {exc}"
        )


def _init_database(db_path):
    """Create Access database and required tables if they do not exist."""
    _create_database_file(db_path)

    conn = pyodbc.connect(_get_connection_string(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE paths_registry (
                id AUTOINCREMENT PRIMARY KEY,
                path TEXT(255) NOT NULL,
                engine TEXT(255),
                date_tested TEXT(255),
                date_added DATETIME,
                added_by TEXT(255),
                created_at DATETIME
            )
            """
        )
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX idx_paths_registry_path ON paths_registry (path)")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute(
            """
            CREATE TABLE master_data (
                id AUTOINCREMENT PRIMARY KEY,
                lookup_key TEXT(255),
                source_path TEXT(255),
                source_file TEXT(255),
                parent_folder TEXT(255),
                engine TEXT(255),
                date_tested TEXT(255),
                date_tested_key TEXT(64),
                perf_point TEXT(255),
                data_col_index INTEGER,
                created_at DATETIME
            )
            """
        )
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX idx_master_lookup_key ON master_data (lookup_key)")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute(
            """
            CREATE TABLE parameters (
                id AUTOINCREMENT PRIMARY KEY,
                param_name TEXT(255) NOT NULL,
                column_name TEXT(64) NOT NULL,
                param_value TEXT(255),
                is_formula BIT,
                created_at DATETIME
            )
            """
        )
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX idx_parameters_name ON parameters (param_name)")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX idx_parameters_column ON parameters (column_name)")
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


def _list_table_columns(cursor, table_name):
    """Return the existing physical column names for a table."""
    return {row.column_name for row in cursor.columns(table=table_name)}


def _load_parameter_rows(cursor):
    """Return parameter metadata keyed by original parameter name."""
    cursor.execute(
        "SELECT param_name, column_name, param_value, is_formula FROM parameters ORDER BY id"
    )
    return {
        row[0]: {
            "column_name": row[1],
            "param_value": row[2],
            "is_formula": bool(row[3]),
        }
        for row in cursor.fetchall()
    }


def _make_unique_column_name(param_name, taken_names):
    """Allocate a unique safe physical column name."""
    base_name = _sanitize_column_name(param_name)
    candidate = base_name
    suffix = 2
    lowered_taken = {name.lower() for name in taken_names}
    while candidate.lower() in lowered_taken:
        suffix_text = f"_{suffix}"
        candidate = f"{base_name[: max(1, 48 - len(suffix_text))]}{suffix_text}"
        suffix += 1
    return candidate


def ensure_parameter_columns(conn, param_names, definitions=None, parameter_rows=None, table_columns=None):
    """Ensure each requested parameter has metadata and a physical master_data column."""
    cursor = conn.cursor()
    definitions = definitions or {}
    parameter_rows = parameter_rows or _load_parameter_rows(cursor)
    table_columns = table_columns or _list_table_columns(cursor, MASTER_TABLE)
    used_column_names = set(table_columns)
    used_column_names.update(meta["column_name"] for meta in parameter_rows.values())

    changed = False
    for raw_name in param_names:
        param_name = str(raw_name or "").strip()
        if not param_name:
            continue

        meta = parameter_rows.get(param_name)
        if meta is None:
            column_name = _make_unique_column_name(param_name, used_column_names)
            definition = definitions.get(param_name, {})
            cursor.execute(
                """
                INSERT INTO parameters (param_name, column_name, param_value, is_formula, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    param_name,
                    column_name,
                    definition.get("param_value"),
                    1 if definition.get("is_formula") else 0,
                    datetime.now(),
                ),
            )
            parameter_rows[param_name] = {
                "column_name": column_name,
                "param_value": definition.get("param_value"),
                "is_formula": bool(definition.get("is_formula")),
            }
            used_column_names.add(column_name)
            meta = parameter_rows[param_name]
            changed = True

        column_name = meta["column_name"]
        if column_name not in table_columns:
            cursor.execute(
                f"ALTER TABLE {MASTER_TABLE} ADD COLUMN {_quote_identifier(column_name)} TEXT(255)"
            )
            table_columns.add(column_name)
            changed = True

    if changed:
        conn.commit()

    cursor.close()
    return parameter_rows, table_columns


def add_parameter(param_name, param_value=None, is_formula=False, db_path=None):
    """Register a parameter and ensure its physical master_data column exists."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    try:
        parameter_rows, _ = ensure_parameter_columns(
            conn,
            [param_name],
            definitions={
                param_name: {
                    "param_value": param_value,
                    "is_formula": is_formula,
                }
            },
        )
        meta = parameter_rows.get(param_name, {})
        return {
            "ok": True,
            "message": f"Parameter '{param_name}' registered.",
            "column_name": meta.get("column_name", ""),
        }
    finally:
        conn.close()


def get_all_parameters(db_path=None):
    """Get all registered parameters from the database."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT param_name FROM parameters ORDER BY param_name")
    rows = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return rows


def add_path_registry_entry(new_path, db_path=None, added_by=None, engine_name=None):
    """Add a new path to the registry with metadata."""
    normalized_path = os.path.normpath(str(new_path or "").strip())
    if not normalized_path:
        return {"ok": False, "message": "Path is empty."}

    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM paths_registry WHERE path = ?", (normalized_path,))
        if cursor.fetchone():
            return {"ok": False, "message": "Path already exists in registry."}

        preview = preview_run_file(normalized_path)
        detected_engine = ""
        if preview.get("ok") and preview.get("engine_detected"):
            detected_engine = str(preview.get("engine") or "").strip()

        selected_engine = str(engine_name or "").strip() or detected_engine or _fallback_engine_name(normalized_path)
        date_tested = _extract_latest_test_date(normalized_path)
        user = added_by or _get_windows_user()
        now = datetime.now()

        cursor.execute(
            """
            INSERT INTO paths_registry (path, engine, date_tested, date_added, added_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (normalized_path, selected_engine, date_tested or None, now, user, now),
        )
        conn.commit()

        return {
            "ok": True,
            "message": "Path added.",
            "record": {
                "Path": normalized_path,
                "Engine": selected_engine,
                "Date_Tested": date_tested,
                "Date_Added": now.strftime("%Y-%m-%d %H:%M:%S"),
                "Added_By": user,
            },
        }
    except Exception as exc:
        return {"ok": False, "message": f"Error adding path: {exc}"}
    finally:
        cursor.close()
        conn.close()


def get_latest_paths(limit=100, db_path=None):
    """Get latest registry entries as records sorted by date_added descending."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()

    top_clause = f"TOP {int(limit)} " if limit and int(limit) > 0 else ""
    cursor.execute(
        f"""
        SELECT {top_clause}path, engine, date_tested, date_added, added_by
        FROM paths_registry
        ORDER BY date_added DESC, id DESC
        """
    )
    rows = cursor.fetchall()
    cursor.close()
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


def upsert_master_record(record, conn=None, db_path=None, parameter_rows=None, table_columns=None):
    """Insert or update one matched run column as a wide Access row."""
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection(db_path=db_path)

    cursor = conn.cursor()
    try:
        parameter_rows, table_columns = ensure_parameter_columns(
            conn,
            list((record.get("param_values") or {}).keys()),
            parameter_rows=parameter_rows,
            table_columns=table_columns,
        )

        lookup_key = _build_lookup_key(
            record.get("path"),
            record.get("date_key"),
            record.get("perf_point"),
        )
        base_payload = {
            "lookup_key": lookup_key,
            "source_path": record.get("path"),
            "source_file": record.get("source_file"),
            "parent_folder": record.get("parent_folder"),
            "engine": record.get("engine"),
            "date_tested": record.get("date_tested"),
            "date_tested_key": record.get("date_key"),
            "perf_point": record.get("perf_point"),
            "data_col_index": record.get("data_col"),
        }

        wide_payload = {}
        for param_name, value in (record.get("param_values") or {}).items():
            meta = parameter_rows.get(param_name)
            if meta:
                wide_payload[meta["column_name"]] = _normalize_db_value(value)

        cursor.execute("SELECT id FROM master_data WHERE lookup_key = ?", (lookup_key,))
        existing_row = cursor.fetchone()

        if existing_row:
            update_payload = dict(base_payload)
            update_payload.update(wide_payload)
            update_columns = [key for key in update_payload.keys() if key != "lookup_key"]
            if update_columns:
                assignments = ", ".join(
                    f"{_quote_identifier(column_name)} = ?" for column_name in update_columns
                )
                values = [update_payload[column_name] for column_name in update_columns]
                values.append(lookup_key)
                cursor.execute(
                    f"UPDATE master_data SET {assignments} WHERE lookup_key = ?",
                    values,
                )
                conn.commit()
            result = {"ok": True, "action": "updated", "id": existing_row[0]}
        else:
            insert_payload = dict(base_payload)
            insert_payload["created_at"] = datetime.now()
            insert_payload.update(wide_payload)
            column_names = list(insert_payload.keys())
            placeholders = ", ".join("?" for _ in column_names)
            cursor.execute(
                f"INSERT INTO master_data ({', '.join(_quote_identifier(name) for name in column_names)}) VALUES ({placeholders})",
                [insert_payload[name] for name in column_names],
            )
            conn.commit()
            result = {"ok": True, "action": "inserted"}

        result["parameter_rows"] = parameter_rows
        result["table_columns"] = table_columns
        return result
    finally:
        cursor.close()
        if owns_connection and conn is not None:
            conn.close()


def store_lookup_columns(run_path, db_path=None, engine_override=None, tracked_params=None, conn=None, parameter_rows=None, table_columns=None):
    """Scan one run file and upsert every matching test column into Access."""
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection(db_path=db_path)

    stats = {"rows_seen": 0, "inserted": 0, "updated": 0}
    try:
        for record in iter_lookup_columns(
            run_path,
            engine_override=engine_override,
            tracked_params=tracked_params,
        ):
            stats["rows_seen"] += 1
            result = upsert_master_record(
                record,
                conn=conn,
                parameter_rows=parameter_rows,
                table_columns=table_columns,
            )
            parameter_rows = result.get("parameter_rows", parameter_rows)
            table_columns = result.get("table_columns", table_columns)
            if result.get("action") == "inserted":
                stats["inserted"] += 1
            elif result.get("action") == "updated":
                stats["updated"] += 1

        stats["parameter_rows"] = parameter_rows
        stats["table_columns"] = table_columns
        return stats
    finally:
        if owns_connection and conn is not None:
            conn.close()


def ingest_all_parameters_from_paths(paths, db_path=None, engine_overrides=None):
    """Bulk-import every available parameter from all registered run columns."""
    conn = get_connection(db_path=db_path)
    parameter_rows = None
    table_columns = None
    totals = {"files": 0, "rows_seen": 0, "inserted": 0, "updated": 0}

    try:
        for path in paths:
            normalized_path = os.path.normpath(str(path or "").strip())
            if not normalized_path or not os.path.exists(normalized_path):
                continue

            override = ""
            if engine_overrides:
                override = str(engine_overrides.get(normalized_path) or engine_overrides.get(path) or "").strip()

            stats = store_lookup_columns(
                normalized_path,
                db_path=db_path,
                engine_override=override,
                tracked_params=None,
                conn=conn,
                parameter_rows=parameter_rows,
                table_columns=table_columns,
            )
            parameter_rows = stats.get("parameter_rows", parameter_rows)
            table_columns = stats.get("table_columns", table_columns)
            totals["files"] += 1
            totals["rows_seen"] += stats.get("rows_seen", 0)
            totals["inserted"] += stats.get("inserted", 0)
            totals["updated"] += stats.get("updated", 0)

        return totals
    finally:
        conn.close()


def backfill_parameter_from_paths(param_name, paths, db_path=None, engine_overrides=None):
    """Backfill one existing parameter column across all registered source files."""
    header = str(param_name or "").strip()
    if not header:
        return {"ok": False, "message": "Parameter name is empty."}

    conn = get_connection(db_path=db_path)
    parameter_rows = None
    table_columns = None
    totals = {"files": 0, "rows_seen": 0, "inserted": 0, "updated": 0}
    try:
        parameter_rows, table_columns = ensure_parameter_columns(conn, [header])
        for path in paths:
            normalized_path = os.path.normpath(str(path or "").strip())
            if not normalized_path or not os.path.exists(normalized_path):
                continue

            override = ""
            if engine_overrides:
                override = str(engine_overrides.get(normalized_path) or engine_overrides.get(path) or "").strip()

            stats = store_lookup_columns(
                normalized_path,
                db_path=db_path,
                engine_override=override,
                tracked_params=[header],
                conn=conn,
                parameter_rows=parameter_rows,
                table_columns=table_columns,
            )
            parameter_rows = stats.get("parameter_rows", parameter_rows)
            table_columns = stats.get("table_columns", table_columns)
            totals["files"] += 1
            totals["rows_seen"] += stats.get("rows_seen", 0)
            totals["inserted"] += stats.get("inserted", 0)
            totals["updated"] += stats.get("updated", 0)

        totals["ok"] = True
        return totals
    finally:
        conn.close()


def fetch_parameter_column(param_name, db_path=None):
    """Fetch one full parameter column plus identifying metadata from Access."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        parameter_rows = _load_parameter_rows(cursor)
        meta = parameter_rows.get(str(param_name or "").strip())
        if not meta:
            return pd.DataFrame(columns=["Engine", "Date_Tested", "Perf. Point", str(param_name or "")])

        column_name = meta["column_name"]
        cursor.execute(
            f"""
            SELECT engine, date_tested, perf_point, {_quote_identifier(column_name)}
            FROM master_data
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=["Engine", "Date_Tested", "Perf. Point", str(param_name or "")])
    finally:
        cursor.close()
        conn.close()


def fetch_master_dataset(required_columns=None, limit=None, db_path=None):
    """Fetch only the requested columns from Access for graphing and table display."""
    if db_path is None:
        db_path = _get_db_path()

    requested = []
    seen = set()
    for column_name in required_columns or []:
        normalized = str(column_name or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        requested.append(normalized)

    if not requested:
        requested = ["Engine", "Date_Tested", "Perf. Point"]

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        parameter_rows = _load_parameter_rows(cursor)
        select_parts = []
        output_columns = []
        selected_aliases = set()

        for requested_name in requested:
            physical_name = DISPLAY_BASE_COLUMNS.get(requested_name)
            if physical_name:
                alias_name = requested_name
                if alias_name in selected_aliases:
                    continue
                select_parts.append(
                    f"{_quote_identifier(physical_name)} AS {_quote_identifier(alias_name)}"
                )
                output_columns.append(alias_name)
                selected_aliases.add(alias_name)
                continue

            param_meta = parameter_rows.get(requested_name)
            if not param_meta:
                continue
            alias_name = requested_name
            if alias_name in selected_aliases:
                continue
            select_parts.append(
                f"{_quote_identifier(param_meta['column_name'])} AS {_quote_identifier(alias_name)}"
            )
            output_columns.append(alias_name)
            selected_aliases.add(alias_name)

        if not select_parts:
            select_parts.append("[engine] AS [Engine]")
            output_columns.append("Engine")

        top_clause = f"TOP {int(limit)} " if limit and int(limit) > 0 else ""
        cursor.execute(
            f"SELECT {top_clause}{', '.join(select_parts)} FROM master_data ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        df = pd.DataFrame.from_records(rows, columns=output_columns)

        for col_name in df.columns:
            if col_name in NON_NUMERIC_COLUMNS:
                continue
            converted = pd.to_numeric(df[col_name], errors="coerce")
            non_null_original = df[col_name].notna().sum()
            non_null_converted = converted.notna().sum()
            if non_null_original and non_null_converted >= max(1, int(non_null_original * 0.7)):
                df[col_name] = converted

        return df
    finally:
        cursor.close()
        conn.close()


def get_master_data_by_date(date_tested, db_path=None):
    """Retrieve a master row by normalized tested date."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        parameter_rows = _load_parameter_rows(cursor)
        normalized_date = _normalize_date_key(date_tested)
        cursor.execute(
            "SELECT TOP 1 * FROM master_data WHERE date_tested_key = ? ORDER BY id DESC",
            (normalized_date,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        column_names = [col[0] for col in cursor.description]
        row_data = dict(zip(column_names, row))
        params = {
            param_name: row_data.get(meta["column_name"])
            for param_name, meta in parameter_rows.items()
            if meta["column_name"] in row_data
        }
        return {
            "engine": row_data.get("engine"),
            "date_tested": row_data.get("date_tested"),
            "perf_point": row_data.get("perf_point"),
            "path": row_data.get("source_path"),
            "params": params,
        }
    finally:
        cursor.close()
        conn.close()


def clear_master_data(db_path=None):
    """Clear all master rows while preserving schema and parameter mappings."""
    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM master_data")
        conn.commit()
        return {"ok": True, "message": "Master data cleared."}
    except Exception as exc:
        return {"ok": False, "message": f"Error clearing data: {exc}"}
    finally:
        cursor.close()
        conn.close()
