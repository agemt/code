"""
Backend switcher for lookup operations.
Supports both Excel (legacy) and Access (optimized) backends.
"""

import os
import sys

# Environment variable to choose backend: "access" (default) or "excel"
BACKEND = os.environ.get("LOOKUP_BACKEND", "access").lower()

# Try to use Access backend if available
if BACKEND == "access":
    try:
        from lookup.loopup_sql_adapter import (
            read_paths_registry,
            get_latest_paths,
            add_path_registry_entry,
            ingest_new_runs,
            retroactive_parameter_update,
            preview_run_file,
            _load_all_params,
            clear_and_rescan,
            fetch_dataset,
        )
        print("✓ Using Access database backend")
    except ImportError as e:
        print(f"⚠ Access backend not available ({e}), falling back to Excel")
        from lookup.loopup import (
            read_paths_registry,
            get_latest_paths,
            add_path_registry_entry,
            ingest_new_runs,
            retroactive_parameter_update,
            preview_run_file,
            _load_all_params,
        )
        clear_and_rescan = None
        fetch_dataset = None
        BACKEND = "excel"
else:
    # Use Excel backend (default/original)
    from lookup.loopup import (
        read_paths_registry,
        get_latest_paths,
        add_path_registry_entry,
        ingest_new_runs,
        retroactive_parameter_update,
        preview_run_file,
        _load_all_params,
    )
    clear_and_rescan = None
    fetch_dataset = None

__all__ = [
    "read_paths_registry",
    "get_latest_paths",
    "add_path_registry_entry",
    "ingest_new_runs",
    "retroactive_parameter_update",
    "preview_run_file",
    "_load_all_params",
    "clear_and_rescan",
    "fetch_dataset",
    "BACKEND",
]
