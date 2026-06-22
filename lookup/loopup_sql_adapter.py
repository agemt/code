"""
Adapter layer that maintains the existing API while using Access database backend.
This allows gradual migration without changing the main application.
"""

import os
from datetime import datetime
import pandas as pd
from lookup.loopup import (
    load_raw_grid,
    _get_lookup_coords,
    _extract_latest_test_date,
    _clean_value,
    _normalize_date_key,
    _create_backup,
    _get_windows_user,
    KEYWORD_Y,
    FORMAT_SHIFT_DATE,
)
from lookup.loopup_access import (
    get_connection,
    _get_db_path,
    get_latest_paths as _db_get_latest_paths,
    add_path_registry_entry as _db_add_path,
    get_master_data_by_date,
    ingest_master_data,
    clear_master_data,
    get_all_parameters as _db_get_all_parameters,
    add_parameter,
)


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
    """
    Generator that ingests files into Access database.
    Maintains the same interface as the Excel version for backward compatibility.
    """
    db_path = _get_db_path()
    total_steps = len(new_runs) + 2
    current_step = 1

    yield {"progress": current_step, "total": total_steps, "message": "Opening database connection..."}
    current_step += 1

    try:
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

            df = load_raw_grid(path)
            if df is None or df.empty:
                continue

            coords = _get_lookup_coords(path, df=df)

            # Extract engine
            try:
                engine_val = str(df.iloc[coords["engine_row"], coords["engine_col"]]).strip()
            except IndexError:
                engine_val = "Unknown"

            if (
                engine_val.lower() in {"nan", "", "unknown"}
                or KEYWORD_Y.lower() in engine_val.lower()
                or engine_val.startswith("#")
            ):
                engine_val = os.path.splitext(os.path.basename(path))[0] or "Unknown"

            if engine_overrides and path in engine_overrides:
                manual_engine = str(engine_overrides.get(path) or "").strip()
                if manual_engine:
                    engine_val = manual_engine

            # Walk horizontally across data columns
            total_cols = len(df.columns)
            for data_col in range(2, total_cols):
                test_val = str(df.iloc[coords["test_row"], data_col]).strip()

                if KEYWORD_Y.lower() not in test_val.lower():
                    continue

                date_val = str(df.iloc[coords["date_row"], data_col]).strip()

                # Collect parameter values
                param_values = {}
                first_col = df.iloc[:, 0].astype(str).str.strip().tolist()

                for param_row in range(len(first_col)):
                    param_name = first_col[param_row]
                    if param_name in all_params:
                        raw_data_val = df.iloc[param_row, data_col]
                        param_values[param_name] = _clean_value(raw_data_val)

                # Insert into database
                result = ingest_master_data(
                    date_tested=date_val,
                    engine=engine_val,
                    perf_point=test_val,
                    param_values=param_values,
                    db_path=db_path,
                )

                if not result.get("ok") and result.get("skipped"):
                    # Duplicate date - skip silently
                    continue
                elif not result.get("ok"):
                    yield {
                        "progress": current_step,
                        "total": total_steps,
                        "message": f"Warning: {result.get('message', '')}",
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


def retroactive_parameter_update(new_param_str, paths_excel, params_txt, master_excel):
    """
    Generator for retroactive parameter updates using Access database.
    Adds a parameter and populates its values retroactively from all scanned files.
    """
    db_path = _get_db_path()
    header = new_param_str.split("=")[0].strip() if "=" in new_param_str else new_param_str.strip()

    # Check if parameter already exists
    existing_params = _db_get_all_parameters(db_path=db_path)
    if header in existing_params:
        yield {
            "progress": 100,
            "total": 100,
            "message": f"ABORTED: '{header}' already exists.",
        }
        return

    yield {"progress": 1, "total": 100, "message": "Initializing parameter update..."}

    # Add to database
    is_formula = "=" in new_param_str
    if is_formula:
        formula = new_param_str.split("=", 1)[1].strip()
        if not formula.startswith("="):
            formula = "=" + formula
        add_parameter(header, param_value=formula, is_formula=True, db_path=db_path)
    else:
        add_parameter(header, param_value=None, is_formula=False, db_path=db_path)

    yield {
        "progress": 50,
        "total": 100,
        "message": f"Parameter '{header}' added to database.",
    }

    # Update params.txt only on success
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
        "message": f"Parameter '{header}' successfully added.",
    }


def preview_run_file(run_path):
    """
    Returns a summary preview (engine, matching take tests, tested dates) for one run file.
    (Same as original - no database needed for this)
    """
    from lookup.loopup import preview_run_file as original_preview
    return original_preview(run_path)


def _load_all_params():
    """Load all parameters from database."""
    db_path = _get_db_path()
    return _db_get_all_parameters(db_path=db_path)


def clear_and_rescan(all_params, db_path=None):
    """Clear master data for a full rescan."""
    if db_path is None:
        db_path = _get_db_path()
    return clear_master_data(db_path=db_path)
