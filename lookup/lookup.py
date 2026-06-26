import csv
import getpass
import json
import os
import re
import shutil
from datetime import datetime

import pandas as pd

try:
    import pyodbc
except Exception:
    pyodbc = None

KEYWORD_Y = "Take"
FORMAT_SHIFT_DATE = datetime(2024, 3, 15)
PATH_REGISTRY_COLUMNS = ["Path", "Engine", "Date_Tested", "Date_Added", "Added_By"]

DATA_TABLE = "Data"
PATHS_TABLE = "Paths"
PARAMS_TABLE = "Params"


def _create_backup(filepath):
    if not os.path.exists(filepath):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.{timestamp}.bak"
    shutil.copy2(filepath, backup_path)

    directory = os.path.dirname(filepath) or "."
    filename = os.path.basename(filepath)
    backups = sorted(
        [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.startswith(f"{filename}.") and f.endswith(".bak")
        ],
        key=os.path.getmtime,
    )
    for old_backup in backups[:-2]:
        try:
            os.remove(old_backup)
        except OSError:
            pass
    return backup_path


def _clean_value(raw_val):
    if pd.isna(raw_val):
        return None

    val_str = str(raw_val).strip()
    if val_str.lower() in ["nan", "none", ""]:
        return None

    val_str = val_str.replace(",", ".")
    try:
        numeric_val = float(val_str)
        return int(numeric_val) if numeric_val.is_integer() else numeric_val
    except ValueError:
        return val_str


def _normalize_date_key(value):
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "none"}:
        return ""

    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    return raw


def _normalize_test_key(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw.lower()


def _format_datetime_for_storage(value):
    """Normalizes datetime values to a stable storage format when possible."""
    normalized = _normalize_date_key(value)
    return normalized if normalized else ""


def _resolve_default_database_path():
    base_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    cfg_path = os.path.join(base_dir, "config.json")
    if not os.path.exists(cfg_path):
        return os.path.join(base_dir, "A.accdb")

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        configured = str(cfg.get("data_source", {}).get("file_path", "")).strip()
    except Exception:
        configured = ""

    if not configured:
        return os.path.join(base_dir, "A.accdb")

    if os.path.isabs(configured):
        return os.path.normpath(configured)
    return os.path.normpath(os.path.join(base_dir, configured))


def _default_paths_registry_path():
    db_path = _resolve_default_database_path()
    if _is_access_path(db_path):
        return db_path

    lookup_dir = os.path.dirname(os.path.abspath(__file__))
    txt_path = os.path.join(lookup_dir, "paths.txt")
    return txt_path


def _is_access_path(path_value):
    ext = os.path.splitext(str(path_value or ""))[1].lower()
    return ext in {".accdb", ".mdb"}


def _quote_ident(name):
    return "[" + str(name).replace("]", "]]" ) + "]"


def _get_windows_user():
    return os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser() or "unknown"


def _fallback_engine_name(path):
    normalized_path = os.path.normpath(str(path or "").strip())
    parent_name = os.path.basename(os.path.dirname(normalized_path)).strip()
    if parent_name:
        return parent_name
    return os.path.splitext(os.path.basename(normalized_path))[0].strip() or "Unknown"


def _describe_path(path):
    normalized_path = os.path.normpath(str(path or "").strip())
    filename = os.path.basename(normalized_path)
    parent_name = os.path.basename(os.path.dirname(normalized_path)).strip()
    if parent_name and filename:
        return f"{parent_name}\\{filename}"
    return filename or normalized_path


def _ensure_pyodbc():
    if pyodbc is None:
        raise RuntimeError("pyodbc is required for Access DB support. Install pyodbc in this environment.")


def _connect_access(db_path):
    _ensure_pyodbc()
    normalized = os.path.normpath(str(db_path or "").strip())
    if not normalized:
        raise ValueError("Database path is empty.")
    if not os.path.exists(normalized):
        raise FileNotFoundError(f"Access DB not found: {normalized}")

    conn_str = (
        "Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={normalized};"
        "ExtendedAnsiSQL=1;"
    )
    return pyodbc.connect(conn_str)


def _table_exists(conn, table_name):
    cursor = conn.cursor()
    rows = cursor.tables(table=table_name, tableType="TABLE").fetchall()
    return bool(rows)


def _get_table_columns(conn, table_name):
    cursor = conn.cursor()
    rows = cursor.columns(table=table_name).fetchall()
    return [str(row.column_name) for row in rows]


def _ensure_column(conn, table_name, column_name, access_type="LONGTEXT"):
    existing = {c.lower() for c in _get_table_columns(conn, table_name)}
    if str(column_name).lower() in existing:
        return

    cursor = conn.cursor()
    cursor.execute(
        f"ALTER TABLE {_quote_ident(table_name)} "
        f"ADD COLUMN {_quote_ident(column_name)} {access_type}"
    )


def _ensure_data_table(conn, dynamic_headers=None):
    if not _table_exists(conn, DATA_TABLE):
        conn.cursor().execute(
            f"CREATE TABLE {_quote_ident(DATA_TABLE)} ("
            "[Engine] TEXT(255),"
            "[Date_Tested] TEXT(64),"
            "[Perf. Point] TEXT(255)"
            ")"
        )

    for header in dynamic_headers or []:
        if header in {"Engine", "Date_Tested", "Perf. Point"}:
            continue
        _ensure_column(conn, DATA_TABLE, header, "LONGTEXT")


def _ensure_paths_table(conn):
    if not _table_exists(conn, PATHS_TABLE):
        conn.cursor().execute(
            f"CREATE TABLE {_quote_ident(PATHS_TABLE)} ("
            "[Path] LONGTEXT,"
            "[Engine] TEXT(255),"
            "[Date_Tested] TEXT(64),"
            "[Date_Added] TEXT(64),"
            "[Added_By] TEXT(255)"
            ")"
        )

    for col in PATH_REGISTRY_COLUMNS:
        if col == "Path":
            _ensure_column(conn, PATHS_TABLE, col, "LONGTEXT")
        else:
            _ensure_column(conn, PATHS_TABLE, col, "TEXT(255)")


def _ensure_params_table(conn):
    if not _table_exists(conn, PARAMS_TABLE):
        conn.cursor().execute(
            f"CREATE TABLE {_quote_ident(PARAMS_TABLE)} ("
            "[Param_Text] LONGTEXT,"
            "[Header] TEXT(255),"
            "[Created_At] TEXT(64),"
            "[Created_By] TEXT(255)"
            ")"
        )

    _ensure_column(conn, PARAMS_TABLE, "Param_Text", "LONGTEXT")
    _ensure_column(conn, PARAMS_TABLE, "Header", "TEXT(255)")
    _ensure_column(conn, PARAMS_TABLE, "Created_At", "TEXT(64)")
    _ensure_column(conn, PARAMS_TABLE, "Created_By", "TEXT(255)")


def _load_table_df(conn, table_name):
    if not _table_exists(conn, table_name):
        return pd.DataFrame()
    query = f"SELECT * FROM {_quote_ident(table_name)}"
    return pd.read_sql(query, conn)


def _normalize_paths_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=PATH_REGISTRY_COLUMNS)

    rename_map = {}
    for col in df.columns:
        if not isinstance(col, str):
            continue
        compact = col.strip().lower().replace("-", "_").replace(" ", "_")
        if compact in {"path", "file_path"}:
            rename_map[col] = "Path"
        elif compact in {"engine", "engine_name"}:
            rename_map[col] = "Engine"
        elif compact in {"date_tested", "test_date"}:
            rename_map[col] = "Date_Tested"
        elif compact in {"date_added", "added_date"}:
            rename_map[col] = "Date_Added"
        elif compact in {"added_by", "who_added", "user"}:
            rename_map[col] = "Added_By"

    normalized = df.rename(columns=rename_map).copy()

    if "Path" not in normalized.columns and len(normalized.columns) == 1:
        normalized = normalized.rename(columns={normalized.columns[0]: "Path"})

    for col in PATH_REGISTRY_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = ""

    return normalized


def _extract_latest_test_date(run_path):
    if not run_path or not os.path.exists(run_path):
        return ""

    df = load_raw_grid(run_path)
    if df is None or df.empty:
        return ""

    coords = _get_lookup_coords(run_path, df=df)
    date_candidates = []
    raw_fallback = []

    total_cols = len(df.columns)
    for data_col in range(2, total_cols):
        try:
            test_val = str(df.iloc[coords["test_row"], data_col]).strip()
        except Exception:
            continue

        if KEYWORD_Y.lower() not in test_val.lower():
            continue

        try:
            raw_date_val = df.iloc[coords["date_row"], data_col]
        except Exception:
            continue

        if pd.isna(raw_date_val):
            continue

        raw_date_str = str(raw_date_val).strip()
        if raw_date_str:
            raw_fallback.append(raw_date_str)

        parsed = pd.to_datetime(raw_date_val, errors="coerce")
        if pd.notna(parsed):
            date_candidates.append(parsed)

    if date_candidates:
        latest = max(date_candidates)
        return latest.strftime("%Y-%m-%d %H:%M:%S")

    return raw_fallback[-1] if raw_fallback else ""


def preview_run_file(run_path):
    normalized_path = str(run_path or "").strip()
    if not normalized_path:
        return {"ok": False, "message": "Path is empty."}

    normalized_path = os.path.normpath(normalized_path)
    if not os.path.exists(normalized_path):
        return {"ok": False, "message": f"File not found: {normalized_path}"}

    df = load_raw_grid(normalized_path)
    if df is None or df.empty:
        return {"ok": False, "message": "Unable to parse file content."}

    coords = _get_lookup_coords(normalized_path, df=df)
    try:
        engine_val = str(df.iloc[coords["engine_row"], coords["engine_col"]]).strip()
    except Exception:
        engine_val = ""

    engine_detected = True
    if (
        not engine_val
        or engine_val.lower() in {"nan", "unknown"}
        or KEYWORD_Y.lower() in engine_val.lower()
        or engine_val.startswith("#")
    ):
        engine_detected = False
        engine_val = ""

    take_tests = []
    tested_dates = []
    for data_col in range(2, len(df.columns)):
        try:
            test_val = str(df.iloc[coords["test_row"], data_col]).strip()
        except Exception:
            continue

        if KEYWORD_Y.lower() not in test_val.lower():
            continue

        take_tests.append(test_val)
        try:
            raw_date_val = df.iloc[coords["date_row"], data_col]
            if pd.notna(raw_date_val):
                tested_dates.append(str(raw_date_val).strip())
        except Exception:
            pass

    return {
        "ok": True,
        "path": normalized_path,
        "engine": engine_val,
        "engine_detected": engine_detected,
        "take_tests": take_tests,
        "tested_dates": tested_dates,
        "message": f"Found {len(take_tests)} matching '{KEYWORD_Y}' test columns.",
    }


def read_paths_registry(paths_registry=None, latest_first=True):
    registry_path = paths_registry or _default_paths_registry_path()

    if _is_access_path(registry_path):
        with _connect_access(registry_path) as conn:
            _ensure_paths_table(conn)
            raw = _load_table_df(conn, PATHS_TABLE)
    else:
        if not os.path.exists(registry_path) or os.path.getsize(registry_path) == 0:
            return pd.DataFrame(columns=PATH_REGISTRY_COLUMNS)
        try:
            raw = pd.read_csv(registry_path, encoding="utf-8-sig")
        except Exception:
            with open(registry_path, "r", encoding="utf-8-sig") as f:
                rows = [line.strip() for line in f if line.strip()]
            raw = pd.DataFrame({"Path": rows})

    normalized = _normalize_paths_df(raw)
    normalized["Path"] = normalized["Path"].astype(str).str.strip()
    normalized = normalized[normalized["Path"] != ""]

    if latest_first and not normalized.empty:
        added_sort = pd.to_datetime(normalized["Date_Added"], errors="coerce")
        normalized = (
            normalized.assign(_added_sort=added_sort)
            .sort_values(by="_added_sort", ascending=False, na_position="last")
            .drop(columns=["_added_sort"])
            .reset_index(drop=True)
        )

    return normalized


def _write_paths_registry(df, paths_registry=None):
    registry_path = paths_registry or _default_paths_registry_path()
    out_df = _normalize_paths_df(df)
    ordered_cols = PATH_REGISTRY_COLUMNS + [c for c in out_df.columns if c not in PATH_REGISTRY_COLUMNS]
    out_df = out_df[ordered_cols].copy()

    if _is_access_path(registry_path):
        with _connect_access(registry_path) as conn:
            _ensure_paths_table(conn)
            for col in out_df.columns:
                _ensure_column(conn, PATHS_TABLE, col, "LONGTEXT")

            cur = conn.cursor()
            cur.execute(f"DELETE FROM {_quote_ident(PATHS_TABLE)}")

            if not out_df.empty:
                col_clause = ", ".join(_quote_ident(c) for c in out_df.columns)
                ph = ", ".join(["?"] * len(out_df.columns))
                sql = f"INSERT INTO {_quote_ident(PATHS_TABLE)} ({col_clause}) VALUES ({ph})"
                for _, row in out_df.iterrows():
                    values = [None if pd.isna(row[c]) else str(row[c]) for c in out_df.columns]
                    cur.execute(sql, values)

            conn.commit()
        return

    out_df.to_csv(registry_path, index=False, encoding="utf-8-sig")


def add_path_registry_entry(new_path, paths_registry=None, added_by=None, engine_name=None):
    normalized_path = str(new_path or "").strip()
    if not normalized_path:
        return {"ok": False, "message": "Path is empty."}

    normalized_path = os.path.normpath(normalized_path)
    current_df = read_paths_registry(paths_registry=paths_registry, latest_first=False)

    existing = current_df["Path"].astype(str).str.lower().str.strip().tolist() if not current_df.empty else []
    if normalized_path.lower() in existing:
        return {"ok": False, "message": "Path already exists in registry."}

    preview = preview_run_file(normalized_path)
    detected_engine = ""
    if preview.get("ok") and preview.get("engine_detected"):
        detected_engine = str(preview.get("engine") or "").strip()

    selected_engine = str(engine_name or "").strip() or detected_engine or _fallback_engine_name(normalized_path)

    record = {
        "Path": normalized_path,
        "Engine": selected_engine,
        "Date_Tested": _format_datetime_for_storage(_extract_latest_test_date(normalized_path)),
        "Date_Added": _format_datetime_for_storage(datetime.now()),
        "Added_By": (added_by or _get_windows_user()),
    }

    updated = pd.concat([current_df, pd.DataFrame([record])], ignore_index=True)
    _write_paths_registry(updated, paths_registry=paths_registry)
    return {"ok": True, "message": "Path added.", "record": record}


def get_latest_paths(limit=100, paths_registry=None):
    df = read_paths_registry(paths_registry=paths_registry, latest_first=True)
    if limit and limit > 0:
        df = df.head(limit)
    return df.to_dict("records")


def load_raw_grid(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in [".xlsx", ".xls"]:
            engine = "openpyxl" if ext == ".xlsx" else "xlrd"
            return pd.read_excel(path, engine=engine, header=None)

        for enc in ["utf-8-sig", "utf-16", "latin1"]:
            try:
                return pd.read_csv(
                    path,
                    sep=None,
                    engine="python",
                    header=None,
                    quoting=csv.QUOTE_NONE,
                    escapechar="\\",
                    on_bad_lines="skip",
                    encoding=enc,
                )
            except Exception:
                continue
    except Exception:
        pass
    return None


def _get_lookup_coords(filepath, df=None):
    if df is not None and not df.empty and len(df.columns) > 2:
        max_scan_rows = min(8, len(df))
        detected_test_row = None
        best_take_hits = 0

        for r_idx in range(max_scan_rows):
            take_hits = 0
            for c_idx in range(2, len(df.columns)):
                raw_val = df.iloc[r_idx, c_idx]
                if pd.isna(raw_val):
                    continue
                if KEYWORD_Y.lower() in str(raw_val).lower():
                    take_hits += 1

            if take_hits > best_take_hits:
                best_take_hits = take_hits
                detected_test_row = r_idx

        if detected_test_row is not None and best_take_hits > 0:
            date_row = min(detected_test_row + 1, len(df) - 1)
            engine_row = max(detected_test_row - 1, 0)
            return {
                "engine_row": engine_row,
                "engine_col": 2,
                "test_row": detected_test_row,
                "date_row": date_row,
            }

    file_ctime = datetime.fromtimestamp(os.path.getctime(filepath))
    if file_ctime > FORMAT_SHIFT_DATE:
        return {"engine_row": 0, "engine_col": 2, "test_row": 1, "date_row": 2}
    return {"engine_row": 0, "engine_col": 2, "test_row": 1, "date_row": 2}


def _insert_data_row(conn, row_dict):
    columns = list(row_dict.keys())
    values = [row_dict[c] for c in columns]
    col_clause = ", ".join(_quote_ident(c) for c in columns)
    ph = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO {_quote_ident(DATA_TABLE)} ({col_clause}) VALUES ({ph})"
    conn.cursor().execute(sql, values)


def _existing_date_keys(conn):
    _ensure_data_table(conn)
    df = _load_table_df(conn, DATA_TABLE)
    if df.empty or "Date_Tested" not in df.columns:
        return set()
    return {
        _normalize_date_key(v)
        for v in df["Date_Tested"].tolist()
        if _normalize_date_key(v)
    }


def reset_data_table(master_db=None):
    db_path = master_db or _resolve_default_database_path()
    with _connect_access(db_path) as conn:
        _ensure_data_table(conn)
        conn.cursor().execute(f"DELETE FROM {_quote_ident(DATA_TABLE)}")
        conn.commit()


def get_all_params(master_db=None):
    db_path = master_db or _resolve_default_database_path()
    params = []

    if _is_access_path(db_path) and os.path.exists(db_path):
        with _connect_access(db_path) as conn:
            _ensure_params_table(conn)
            df = _load_table_df(conn, PARAMS_TABLE)
            if not df.empty and "Param_Text" in df.columns:
                for raw in df["Param_Text"].tolist():
                    line = str(raw or "").strip()
                    if not line:
                        continue
                    params.append(line)
                    if "=" in line:
                        params.append(line.split("=", 1)[0].strip())

    if not params:
        txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "params.txt")
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8-sig") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    params.append(line)
                    if "=" in line:
                        params.append(line.split("=", 1)[0].strip())

    seen = set()
    unique = []
    for p in params:
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


def _append_param_definition(new_param_str, master_db=None):
    db_path = master_db or _resolve_default_database_path()
    header = new_param_str.split("=", 1)[0].strip() if "=" in new_param_str else new_param_str.strip()

    with _connect_access(db_path) as conn:
        _ensure_params_table(conn)
        df = _load_table_df(conn, PARAMS_TABLE)

        existing_lines = set(df.get("Param_Text", pd.Series(dtype=str)).astype(str).str.strip().tolist())
        existing_headers = set(df.get("Header", pd.Series(dtype=str)).astype(str).str.strip().tolist())
        if new_param_str in existing_lines or header in existing_headers:
            return False

        sql = (
            f"INSERT INTO {_quote_ident(PARAMS_TABLE)} "
            "([Param_Text], [Header], [Created_At], [Created_By]) VALUES (?, ?, ?, ?)"
        )
        conn.cursor().execute(
            sql,
            [
                new_param_str,
                header,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                _get_windows_user(),
            ],
        )
        conn.commit()
    return True


def _row_formula_value(formula_text, row_values):
    expression = str(formula_text or "").strip()
    if expression.startswith("="):
        expression = expression[1:]

    col_refs = re.findall(r"\[([^\]]+)\]", expression)
    token_map = {}
    eval_expr = expression

    for idx, col_name in enumerate(col_refs):
        token = f"v{idx}"
        raw_val = row_values.get(col_name)
        num_val = pd.to_numeric(pd.Series([raw_val]), errors="coerce").iloc[0]
        token_map[token] = 0.0 if pd.isna(num_val) else float(num_val)
        eval_expr = eval_expr.replace(f"[{col_name}]", token)

    try:
        return eval(eval_expr, {"__builtins__": {}}, token_map)
    except Exception:
        return None


def ingest_new_runs(new_runs, all_params, master_excel, engine_overrides=None):
    db_path = master_excel or _resolve_default_database_path()
    total_steps = len(new_runs) + 2
    current_step = 1

    yield {"progress": current_step, "total": total_steps, "message": "Backing up database..."}
    _create_backup(db_path)
    current_step += 1

    with _connect_access(db_path) as conn:
        _ensure_data_table(conn, dynamic_headers=all_params)
        existing_date_keys = _existing_date_keys(conn)

        for idx, path in enumerate(new_runs, start=1):
            path_label = _describe_path(path)
            yield {
                "progress": current_step,
                "total": total_steps,
                "message": f"Processing [{idx}/{len(new_runs)}]: {path_label}",
            }
            current_step += 1

            df = load_raw_grid(path)
            if df is None or df.empty:
                continue

            coords = _get_lookup_coords(path, df=df)

            try:
                engine_val = str(df.iloc[coords["engine_row"], coords["engine_col"]]).strip()
            except IndexError:
                engine_val = "Unknown"

            if (
                engine_val.lower() in {"nan", "", "unknown"}
                or KEYWORD_Y.lower() in engine_val.lower()
                or engine_val.startswith("#")
            ):
                engine_val = _fallback_engine_name(path)

            if engine_overrides and path in engine_overrides:
                manual_engine = str(engine_overrides.get(path) or "").strip()
                if manual_engine:
                    engine_val = manual_engine

            first_col = df.iloc[:, 0].astype(str).str.strip().tolist()
            total_rows = len(df)
            total_cols = len(df.columns)

            for data_col in range(2, total_cols):
                test_val = str(df.iloc[coords["test_row"], data_col]).strip()
                if KEYWORD_Y.lower() not in test_val.lower():
                    continue

                date_val = str(df.iloc[coords["date_row"], data_col]).strip()
                date_key = _normalize_date_key(date_val)
                if date_key and date_key in existing_date_keys:
                    continue

                row_out = {
                    "Engine": engine_val,
                    "Date_Tested": date_val,
                    "Perf. Point": test_val,
                }

                for param_row in range(total_rows):
                    param_name = first_col[param_row]
                    if param_name in all_params:
                        _ensure_column(conn, DATA_TABLE, param_name, "LONGTEXT")
                        row_out[param_name] = _clean_value(df.iloc[param_row, data_col])

                _insert_data_row(conn, row_out)
                if date_key:
                    existing_date_keys.add(date_key)

        conn.commit()

    yield {"progress": total_steps - 1, "total": total_steps, "message": "Finalizing inserts..."}
    yield {"progress": total_steps, "total": total_steps, "message": "Ingestion complete."}


def retroactive_parameter_update(new_param_str, paths_excel, params_txt, master_excel):
    del params_txt
    db_path = master_excel or paths_excel or _resolve_default_database_path()
    header = new_param_str.split("=", 1)[0].strip() if "=" in new_param_str else new_param_str.strip()

    existing = get_all_params(master_db=db_path)
    if new_param_str in existing or header in existing:
        yield {
            "progress": 100,
            "total": 100,
            "message": f"ABORTED: '{header}' already exists in Params table.",
        }
        return

    yield {"progress": 1, "total": 100, "message": "Initializing parameter update..."}
    _create_backup(db_path)

    with _connect_access(db_path) as conn:
        _ensure_data_table(conn)
        _ensure_column(conn, DATA_TABLE, header, "LONGTEXT")

        if "=" in new_param_str:
            formula = new_param_str.split("=", 1)[1].strip()
            if not formula.startswith("="):
                formula = "=" + formula

            yield {"progress": 45, "total": 100, "message": f"Calculating formula for {header}..."}
            data_df = _load_table_df(conn, DATA_TABLE)
            if not data_df.empty:
                cur = conn.cursor()
                for _, row in data_df.iterrows():
                    row_dict = row.to_dict()
                    computed = _row_formula_value(formula, row_dict)
                    date_val = row_dict.get("Date_Tested")
                    cur.execute(
                        f"UPDATE {_quote_ident(DATA_TABLE)} SET {_quote_ident(header)} = ? "
                        "WHERE [Date_Tested] = ?",
                        [computed, date_val],
                    )
        else:
            config_df = read_paths_registry(paths_registry=paths_excel, latest_first=False)
            if config_df.empty or "Path" not in config_df.columns:
                yield {"progress": 100, "total": 100, "message": "Error: no paths available in registry."}
                return

            data_df = _load_table_df(conn, DATA_TABLE)
            if data_df.empty or "Date_Tested" not in data_df.columns or "Perf. Point" not in data_df.columns:
                yield {
                    "progress": 100,
                    "total": 100,
                    "message": "Error: Data table must contain Date_Tested and Perf. Point columns.",
                }
                return

            # Build deterministic targets: key on exact test instance (Date+Time + Perf. Point).
            master_row_map = {}
            for _, row in data_df.iterrows():
                date_raw = row.get("Date_Tested")
                perf_raw = row.get("Perf. Point")
                date_key = _normalize_date_key(date_raw)
                perf_key = _normalize_test_key(perf_raw)
                if not date_key or not perf_key:
                    continue
                master_row_map.setdefault((date_key, perf_key), []).append(
                    {
                        "date_raw": None if pd.isna(date_raw) else str(date_raw),
                        "perf_raw": None if pd.isna(perf_raw) else str(perf_raw),
                    }
                )

            if not master_row_map:
                yield {
                    "progress": 100,
                    "total": 100,
                    "message": "Error: no valid Date_Tested + Perf. Point keys found in Data table.",
                }
                return

            pending_updates = {}

            total_files = len(config_df)
            for idx, row in config_df.iterrows():
                path = str(row["Path"]).strip()
                yield {
                    "progress": 10 + idx,
                    "total": total_files + 20,
                    "message": f"Scanning: {_describe_path(path)}",
                }

                df = load_raw_grid(path)
                if df is None or df.empty:
                    continue

                coords = _get_lookup_coords(path, df=df)
                first_col = df.iloc[:, 0].astype(str).str.strip().tolist()
                if header not in first_col:
                    continue
                target_param_row = first_col.index(header)

                total_cols = len(df.columns)
                for data_col in range(2, total_cols):
                    test_val = str(df.iloc[coords["test_row"], data_col]).strip()
                    if KEYWORD_Y.lower() not in test_val.lower():
                        continue

                    date_val = str(df.iloc[coords["date_row"], data_col]).strip()
                    date_key = _normalize_date_key(date_val)
                    perf_key = _normalize_test_key(test_val)
                    update_key = (date_key, perf_key)
                    if update_key not in master_row_map:
                        continue

                    raw_data_val = df.iloc[target_param_row, data_col]
                    clean_val = _clean_value(raw_data_val)

                    # Keep source selection deterministic so path sorting does not change results.
                    source_rank = (os.path.normcase(os.path.normpath(path)), data_col)
                    previous = pending_updates.get(update_key)
                    if previous is None or source_rank < previous["source_rank"]:
                        pending_updates[update_key] = {
                            "value": clean_val,
                            "source_rank": source_rank,
                        }

            cur = conn.cursor()
            for update_key in sorted(pending_updates.keys()):
                update_val = pending_updates[update_key]["value"]
                targets = master_row_map.get(update_key, [])
                for target in targets:
                    cur.execute(
                        f"UPDATE {_quote_ident(DATA_TABLE)} SET {_quote_ident(header)} = ? "
                        "WHERE [Date_Tested] = ? AND [Perf. Point] = ?",
                        [update_val, target["date_raw"], target["perf_raw"]],
                    )

        conn.commit()

    _append_param_definition(new_param_str, master_db=db_path)
    yield {"progress": 100, "total": 100, "message": f"Parameter '{header}' successfully added."}
