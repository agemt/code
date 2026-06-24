"""
Adapter layer that maintains the existing API while using Access database backend.
This allows gradual migration without changing the main application.
"""

import os

import pandas as pd

from lookup.loopup_access import (
    _get_db_path,
    add_parameter,
    add_path_registry_entry as _db_add_path,
    backfill_parameter_from_paths,
    clear_master_data,
    fetch_master_dataset,
    get_all_parameters as _db_get_all_parameters,
    get_connection,
    get_latest_paths as _db_get_latest_paths,
    store_lookup_columns,
)


def _load_params_txt():
    """Load tracked parameters from params.txt for app-facing fetch selection."""
    params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "params.txt")
    if not os.path.exists(params_path):
        return []

    params = []
    with open(params_path, "r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            params.append(line)
            if "=" in line:
                params.append(line.split("=", 1)[0].strip())

    seen = set()
    unique = []
    for param_name in params:
        if param_name in seen:
            continue
        seen.add(param_name)
        unique.append(param_name)
    return unique


def read_paths_registry(paths_registry=None, latest_first=True):
    """
    Read paths registry from Access database.
    If paths_registry is provided (for legacy compatibility), it's ignored.
    """
    db_path = _get_db_path()
    rows = _db_get_latest_paths(limit=500, db_path=db_path)
    
    # Convert to DataFrame with proper column names
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=["Path", "Engine", "Date_Tested", "Date_Added", "Added_By"]
        )
    
    return df


def get_latest_paths(limit=100, paths_registry=None):
    """Returns latest registry rows as records sorted by Date_Added descending."""
    db_path = _get_db_path()
    return _db_get_latest_paths(limit=limit, db_path=db_path)


def add_path_registry_entry(new_path, paths_registry=None, added_by=None, engine_name=None):
    """Add a new path with metadata (uses Access database)."""
    db_path = _get_db_path()
    return _db_add_path(
        new_path,
        db_path=db_path,
        added_by=added_by,
        engine_name=engine_name,
    )


def ingest_new_runs(new_runs, all_params, master_excel, engine_overrides=None):
    """Generator that ingests full matched columns into the Access master table."""
    db_path = _get_db_path()
    total_steps = len(new_runs) + 2
    current_step = 1

    yield {"progress": current_step, "total": total_steps, "message": "Opening database connection..."}
    current_step += 1

    conn = None
    try:
        conn = get_connection(db_path)
        parameter_rows = None
        table_columns = None
        for idx, path in enumerate(new_runs, start=1):
            filename = os.path.basename(path)
            yield {
                "progress": current_step,
                "total": total_steps,
                "message": f"Processing [{idx}/{len(new_runs)}]: {filename}",
            }
            current_step += 1

            if not os.path.exists(path):
                continue

            override = None
            if engine_overrides and path in engine_overrides:
                override = str(engine_overrides.get(path) or "").strip() or None

            stats = store_lookup_columns(
                path,
                db_path=db_path,
                engine_override=override,
                tracked_params=None,
                conn=conn,
                parameter_rows=parameter_rows,
                table_columns=table_columns,
            )
            parameter_rows = stats.get("parameter_rows", parameter_rows)
            table_columns = stats.get("table_columns", table_columns)
            yield {
                "progress": current_step - 1,
                "total": total_steps,
                "message": f"Imported {stats.get('rows_seen', 0)} matched columns from {filename}.",
            }

        yield {
            "progress": total_steps - 1,
            "total": total_steps,
            "message": "Finalizing ingestion...",
        }
        yield {
            "progress": total_steps,
            "total": total_steps,
            "message": "Ingestion complete.",
        }
    except Exception as e:
        yield {
            "progress": total_steps,
            "total": total_steps,
            "message": f"Error during ingestion: {e}",
        }
    finally:
        if conn is not None:
            conn.close()


def retroactive_parameter_update(new_param_str, paths_excel, params_txt, master_excel):
    """Backfill one parameter into the wide Access master table."""
    db_path = _get_db_path()
    header = new_param_str.split("=")[0].strip() if "=" in new_param_str else new_param_str.strip()

    yield {"progress": 1, "total": 100, "message": "Initializing parameter update..."}
    is_formula = "=" in new_param_str
    if is_formula:
        formula = new_param_str.split("=", 1)[1].strip()
        if not formula.startswith("="):
            formula = "=" + formula
        add_parameter(header, param_value=formula, is_formula=True, db_path=db_path)
        params_exists = os.path.exists(params_txt)
        if params_exists and os.path.getsize(params_txt) > 0:
            with open(params_txt, "a", encoding="utf-8-sig") as f:
                f.write(f"\n{new_param_str}")
        else:
            with open(params_txt, "w", encoding="utf-8-sig") as f:
                f.write(new_param_str)
        yield {
            "progress": 100,
            "total": 100,
            "message": f"Formula parameter '{header}' registered in Access metadata only.",
        }
        return

    add_parameter(header, param_value=None, is_formula=False, db_path=db_path)
    yield {
        "progress": 10,
        "total": 100,
        "message": f"Parameter '{header}' registered in Access.",
    }

    config_df = read_paths_registry(paths_registry=paths_excel, latest_first=False)
    if config_df.empty or "Path" not in config_df.columns:
        params_exists = os.path.exists(params_txt)
        if params_exists and os.path.getsize(params_txt) > 0:
            with open(params_txt, "a", encoding="utf-8-sig") as f:
                f.write(f"\n{new_param_str}")
        else:
            with open(params_txt, "w", encoding="utf-8-sig") as f:
                f.write(new_param_str)
        yield {"progress": 100, "total": 100, "message": "No paths available in registry; metadata only updated."}
        return

    engine_overrides = {}
    if "Engine" in config_df.columns:
        for _, row in config_df.iterrows():
            path_val = str(row.get("Path", "")).strip()
            eng_val = str(row.get("Engine", "")).strip()
            if path_val and eng_val:
                engine_overrides[path_val] = eng_val

    stats = backfill_parameter_from_paths(
        header,
        config_df["Path"].tolist(),
        db_path=db_path,
        engine_overrides=engine_overrides,
    )

    params_exists = os.path.exists(params_txt)
    if params_exists and os.path.getsize(params_txt) > 0:
        with open(params_txt, "a", encoding="utf-8-sig") as f:
            f.write(f"\n{new_param_str}")
    else:
        with open(params_txt, "w", encoding="utf-8-sig") as f:
            f.write(new_param_str)

    yield {
        "progress": 100,
        "total": 100,
        "message": f"Parameter '{header}' refreshed from {stats.get('rows_seen', 0)} matched columns.",
    }


def preview_run_file(run_path):
    """
    Returns a summary preview (engine, matching take tests, tested dates) for one run file.
    (Same as original - no database needed for this)
    """
    from lookup.loopup import preview_run_file as original_preview
    return original_preview(run_path)


def _load_all_params():
    """Load tracked parameters from params.txt for app-facing workflows."""
    return _load_params_txt()


def fetch_dataset(required_columns=None, limit=None):
    """Fetch only the requested columns from the Access master table."""
    return fetch_master_dataset(required_columns=required_columns, limit=limit, db_path=_get_db_path())


def clear_and_rescan(all_params, db_path=None):
    """Clear master data for a full rescan."""
    if db_path is None:
        db_path = _get_db_path()
    return clear_master_data(db_path=db_path)
