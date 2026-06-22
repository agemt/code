# Lookup Module - Comprehensive Function & Code Guide

**Version**: 2.0 (Dual Backend - Excel & Access)  
**Last Updated**: 2026-06-22  
**Status**: Production Ready

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [Excel Backend (loopup.py)](#excel-backend-loopuppy)
4. [Access Backend (loopup_access.py)](#access-backend-loopup_accesspy)
5. [Integration Layer (loopup_sql_adapter.py)](#integration-layer-loopup_sql_adapterpy)
6. [Data Flow Diagrams](#data-flow-diagrams)
7. [Common Workflows](#common-workflows)
8. [Modification Manual](#modification-manual)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The lookup module is a dual-backend system designed to ingest test data from multiple file formats and maintain a centralized database of parameters and performance metrics.

```
┌─────────────────────────────────────────────┐
│         Dash Application (UI)               │
│        pages/home.py & pages/graph.py       │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │  Backend Switcher   │
        │  lookup/__init__.py  │
        └──────────┬──────────┘
        │          │
        ├──────────┴──────────────┐
        │                         │
    ┌───▼─────────────┐   ┌───────▼──────────┐
    │  Excel Backend  │   │  Access Backend  │
    │  loopup.py      │   │ loopup_access.py │
    │  (Legacy)       │   │ (Optimized)      │
    │  ✓ Default      │   │ ✓ SQL-based      │
    │  ✓ Stable       │   │ ✓ Fast queries   │
    └─────────────────┘   └──────────────────┘
              │                    │
        File-based            Database-based
        (Excel/CSV/TXT)        (Access .accdb)
```

**Backend Selection**:
- **Default**: Excel (backward compatible)
- **Environment Variable**: `LOOKUP_BACKEND=access` or `LOOKUP_BACKEND=excel`
- **Auto-fallback**: If Access unavailable, reverts to Excel

---

## Core Concepts

### 1. **Test Data Structure**

All ingested files follow a consistent spatial layout:

```
Row 0 (optional):     [Title Row - ignored]
Row 1 (engine):       [Engine Name] [?] [Engine/Section Name]...
Row 2 (test):         [?] [?] [Take_B3] [Take_B4] [Take_B6]...
Row 3 (date):         [?] [?] [2024-01-15] [2024-01-16] [2024-01-17]...
Row 4+:               [Param1] [?] [value] [value] [value]...
                      [Param2] [?] [value] [value] [value]...
```

**Spatial Coordinates** (detected via `_get_lookup_coords`):
- **engine_row**: Row containing engine identifier
- **engine_col**: Column 2 (0-indexed)
- **test_row**: Row containing "Take" keyword markers
- **date_row**: Row containing tested dates

### 2. **Parameters**

Parameters are tracked independently and retroactively applied to master data:

- Stored in `lookup/params.txt` (Excel) or `parameters` table (Access)
- Format: `ParamName` or `ParamName=Formula`
- Example with formula: `A1_Power=B2+C2*0.5`
- Matched by name against Column A of test files

### 3. **Uniqueness Constraint**

**Date_Tested is the primary unique key**:
- No duplicate dates in master database
- Duplicate date ingestion is silently skipped
- Same engine can have multiple rows (different dates)
- Date normalization ensures format-agnostic matching

### 4. **Registry System**

Maintains metadata about ingested files:

| Column | Purpose |
|--------|---------|
| Path | Full absolute path to test file |
| Engine | Detected or manually entered engine name |
| Date_Tested | Latest test date from file |
| Date_Added | Timestamp when added to registry |
| Added_By | Windows username who added it |

---

## Excel Backend (loopup.py)

### Function Reference

#### **A. File Parsing**

##### `load_raw_grid(path) → DataFrame`

**Purpose**: Load any text/CSV/Excel file as raw grid (no headers).

**Parameters**:
- `path` (str): Absolute path to test file

**Returns**:
- DataFrame with spatial coordinates intact
- `None` if file unreadable

**Supported Formats**:
- `.xlsx`, `.xls` (openpyxl/xlrd engines)
- `.txt`, `.csv` (UTF-8, UTF-16, Latin-1 encoding detection)

**Example**:
```python
df = load_raw_grid("C:/data/test_B3.txt")
print(df.iloc[0:5, 0:5])  # First 5 rows, first 5 columns
```

**Internal Logic**:
1. Detect file extension
2. Excel files: Use pandas `read_excel` with appropriate engine
3. Text files: Try encodings in order (UTF-8-sig → UTF-16 → Latin-1)
4. Return raw grid with preserved spatial layout

---

##### `_get_lookup_coords(filepath, df=None) → dict`

**Purpose**: Auto-detect metadata row positions using pattern matching.

**Parameters**:
- `filepath` (str): File path (used for fallback date detection)
- `df` (DataFrame, optional): File content. If provided, enables dynamic detection

**Returns**:
```python
{
    "engine_row": 0,      # Row containing engine identifier
    "engine_col": 2,      # Column containing engine (always 2)
    "test_row": 1,        # Row containing "Take" markers
    "date_row": 2,        # Row containing dates
}
```

**Auto-Detection Algorithm**:
1. If DataFrame provided, scan first 8 rows
2. Count "Take" keyword hits in each row across columns 2+
3. Row with most hits = test_row
4. Automatically derive engine_row (test_row - 1) and date_row (test_row + 1)
5. If no "Take" found, use file creation date to pick historical defaults

**Fallback Logic**:
- Files created before 2024-03-15: Legacy format (specific defaults)
- Files created after: Modern format with dynamic detection

**Example**:
```python
df = load_raw_grid("C:/data/test.txt")
coords = _get_lookup_coords("C:/data/test.txt", df=df)
# coords = {"engine_row": 0, "engine_col": 2, "test_row": 1, "date_row": 2}
```

---

#### **B. Data Ingestion**

##### `ingest_new_runs(new_runs, all_params, master_excel, engine_overrides=None)`

**Purpose**: Main ingestion pipeline. Processes list of test files and inserts data into master Excel.

**Parameters**:
- `new_runs` (list[str]): List of absolute file paths to ingest
- `all_params` (list[str]): All valid parameter names (from params.txt)
- `master_excel` (str): Path to master.xlsx destination
- `engine_overrides` (dict, optional): `{filepath: "ManualEngineName", ...}`

**Returns**: Generator yielding progress updates

```python
{
    "progress": 5,
    "total": 10,
    "message": "Processing [2/3]: test_B3.txt"
}
```

**Processing Logic** (Step-by-step):

1. **Backup Creation**: Creates timestamped backup of master.xlsx, retains only 2 most recent

2. **Header Mapping**: Scans Row 1 to build column index map:
   ```python
   header_map = {
       "Engine": 1,
       "Date_Tested": 2,
       "Perf. Point": 3,
       "A01111": 4,
       ...
   }
   ```

3. **Uniqueness Cache**: Loads all existing Date_Tested values into memory set for fast lookup

4. **Per-File Processing**:
   - Extract engine name from detected row
   - If empty/unknown/contains "Take": Use filename as engine
   - Allow override via `engine_overrides` dict
   - Walk horizontally (column by column) starting at column 2

5. **Per-Column (Test) Processing**:
   - Check if column header contains "Take" keyword
   - If yes, this is a valid test column
   - Extract corresponding date from date_row
   - **Uniqueness Check**: If date already exists → skip entire column
   - Insert new row at position 2 (below headers)

6. **Per-Parameter (Vertical) Processing**:
   - For each row in column A (parameters)
   - If parameter name exists in `all_params` AND `header_map`:
     - Extract value from test file (column, row)
     - Clean value (remove commas, convert to number if possible)
     - Write to master Excel at (row 2, param's column)

7. **Finalization**:
   - Expand Excel table bounds to include new data
   - Save workbook
   - Yield completion

**Data Cleaning** (`_clean_value`):
- Handles commas: `1,234.5` → `1234.5`
- Converts to numeric: `"123"` → `123` (int), `"123.5"` → `123.5` (float)
- Preserves text: `"Pass/Fail"` → `"Pass/Fail"`
- Null handling: `NaN`, `"None"`, empty string → `None`

**Date Normalization** (`_normalize_date_key`):
- Input: Any date format (`"1/15/2024"`, `"2024-01-15"`, `"15 Jan 2024"`, etc.)
- Process: Parse with pandas, convert to ISO format
- Output: `"2024-01-15 12:34:56"` (normalized key for comparison)
- Returns empty string if unparseable

**Example**:
```python
all_params = ["A01111", "A01112", "A06611", "A1_Power", "FuelSumL"]
new_files = ["C:/data/test_B3.txt", "C:/data/test_B4.txt"]

for update in ingest_new_runs(new_files, all_params, "master.xlsx"):
    print(f"{update['progress']}/{update['total']}: {update['message']}")
    # Output:
    # 1/4: Backing up master database...
    # 2/4: Processing [1/2]: test_B3.txt
    # 3/4: Processing [2/2]: test_B4.txt
    # 4/4: Ingestion complete.
```

---

##### `preview_run_file(run_path) → dict`

**Purpose**: Quick preview of what a file will ingest before committing.

**Parameters**:
- `run_path` (str): Absolute path to test file

**Returns**:
```python
{
    "ok": True,
    "path": "C:/data/test_B3.txt",
    "engine": "B737_Classic",
    "engine_detected": True,  # False if manual entry required
    "take_tests": ["Take_B3", "Take_B4"],
    "tested_dates": ["2024-01-15", "2024-01-16"],
    "message": "Found 2 matching 'Take' test columns."
}
```

**Error Cases**:
```python
{"ok": False, "message": "Path is empty."}
{"ok": False, "message": "File not found: C:/data/missing.txt"}
{"ok": False, "message": "Unable to parse file content."}
```

**Logic**:
1. Validate path exists
2. Load file as raw grid
3. Auto-detect coordinates
4. Extract engine from detected row
5. Mark `engine_detected=False` if empty/unknown/"Take"/starts with "#"
6. Scan all columns for "Take" keyword
7. Collect all test names and corresponding dates

**Example**:
```python
preview = preview_run_file("C:/data/test_B3.txt")
if preview["ok"] and not preview["engine_detected"]:
    print(f"Manual engine entry required for {preview['path']}")
```

---

#### **C. Registry Management**

##### `read_paths_registry(paths_registry=None, latest_first=True) → DataFrame`

**Purpose**: Load registry data (paths.xlsx or paths.txt) with normalization.

**Parameters**:
- `paths_registry` (str, optional): Custom registry path. Defaults to lookup/paths.xlsx or lookup/paths.txt
- `latest_first` (bool): Sort by Date_Added descending (most recent first)

**Returns**: Normalized DataFrame with columns: `Path`, `Engine`, `Date_Tested`, `Date_Added`, `Added_By`

**Column Normalization** (via `_normalize_paths_df`):

The function maps various naming conventions to canonical names:

| Input Variations | Canonical Name |
|------------------|----------------|
| path, file_path | Path |
| engine, engine_name | Engine |
| date_tested, test_date | Date_Tested |
| date_added, added_date | Date_Added |
| added_by, who_added, user | Added_By |

**Backward Compatibility**:
- Plain text file with single column → Assumes all rows are paths
- Missing columns → Added as empty strings
- Filters out blank paths

**Example**:
```python
df = read_paths_registry()  # Uses default location
print(df)
#                                  Path    Engine   Date_Tested              Date_Added    Added_By
# 0  C:\data\test_latest.txt  B737 Classic 2024-01-16 2024-06-22 14:30:45  Matvey
# 1  C:\data\test_old.txt     B777       2024-01-10 2024-06-21 09:15:22  Matvey
```

---

##### `add_path_registry_entry(new_path, paths_registry=None, added_by=None, engine_name=None) → dict`

**Purpose**: Add a new file path to registry with metadata.

**Parameters**:
- `new_path` (str): Absolute path to test file
- `paths_registry` (str, optional): Custom registry location
- `added_by` (str, optional): Username. Defaults to Windows username
- `engine_name` (str, optional): Manual engine override

**Returns**:
```python
# Success:
{
    "ok": True,
    "message": "Path added.",
    "record": {
        "Path": "C:/data/test_new.txt",
        "Engine": "B737_Classic",
        "Date_Tested": "2024-01-15 08:00:00",
        "Date_Added": "2024-06-22 14:30:45",
        "Added_By": "Matvey"
    }
}

# Error:
{"ok": False, "message": "Path already exists in registry."}
{"ok": False, "message": "Path is empty."}
```

**Logic**:
1. Validate path is not empty
2. Normalize path (convert to Windows format)
3. Load current registry
4. Check for duplicates (case-insensitive)
5. If duplicate found → abort with error
6. Preview file to detect engine (if available)
7. Use manual `engine_name` if provided, else use detected, else use filename
8. Extract latest test date from file
9. Create new record with current timestamp and Windows user
10. Append to registry and persist

**Example**:
```python
result = add_path_registry_entry(
    "C:/data/test_new.txt",
    engine_name="B777"  # Override auto-detection
)
if result["ok"]:
    print(f"Added: {result['record']['Path']}")
else:
    print(f"Error: {result['message']}")
```

---

##### `get_latest_paths(limit=100, paths_registry=None) → list[dict]`

**Purpose**: Get latest registry entries as list of records (convenient format for UI).

**Parameters**:
- `limit` (int): Maximum records to return (default 100)
- `paths_registry` (str, optional): Custom registry path

**Returns**: List of dictionaries with one record per path

```python
[
    {
        "Path": "C:/data/test_new.txt",
        "Engine": "B737_Classic",
        "Date_Tested": "2024-01-15",
        "Date_Added": "2024-06-22 14:30:45",
        "Added_By": "Matvey"
    },
    ...
]
```

**Example**:
```python
latest = get_latest_paths(limit=10)
for record in latest:
    print(f"{record['Path']}: {record['Engine']}")
```

---

#### **D. Parameter Management**

##### `retroactive_parameter_update(new_param_str, paths_excel, params_txt, master_excel)`

**Purpose**: Add a new parameter (with optional formula) and populate it retroactively from all scanned files.

**Parameters**:
- `new_param_str` (str): Parameter name or formula (e.g., `"FuelSumL"` or `"CustomCalc=B2*C2"`)
- `paths_excel` (str): Path to registry file
- `params_txt` (str): Path to params.txt tracking file
- `master_excel` (str): Path to master.xlsx

**Returns**: Generator yielding progress updates

```python
{
    "progress": 50,
    "total": 100,
    "message": "Injecting formula for CustomCalc..."
}
```

**Processing Logic** (Step-by-step):

1. **Parameter Validation**:
   - Extract header name (before "=" if formula)
   - Check if already exists in params.txt
   - Abort if duplicate

2. **Backup Creation**: Creates timestamped backup

3. **Open Workbook**: Load master.xlsx

4. **Column Preparation**:
   - Insert new column at right-most position (max_column + 1)
   - Write header name to cell (row 1)

5. **Formula Injection** (if "=" present in new_param_str):
   - Extract formula portion (after "=")
   - Prepend "=" if missing
   - Write formula to all data rows (row 2 to max_row)
   - Example: `"CustomCalc=B2*C2"` → Excel cells get `=B2*C2`

6. **Retroactive Population** (if formula absent):
   - Build header map of master columns
   - Find Date_Tested column (with alias support)
   - Create lookup map: `{normalized_date_key: row_number}`
   - For each file in registry:
     - Load file as raw grid
     - Find parameter row in column A
     - For each test column (contains "Take"):
       - Extract date from date_row
       - Normalize date key
       - Look up matching row in master
       - Extract parameter value
       - Write to master at found row

7. **Finalization**:
   - Expand Excel table bounds
   - Save workbook
   - **Only on success**: Append to params.txt
   - Yield completion

**Date Matching Strategy**:

The function uses normalized date keys to match retroactively:
- File has date: `"01/15/2024 08:00 AM"` → Normalizes to `"2024-01-15 08:00:00"`
- Master has date: `"2024-01-15T08:00:00"` → Normalizes to `"2024-01-15 08:00:00"`
- Match found → Value populated in master

**Formula Examples**:
```python
# Simple formula (Excel operations)
"CustomCalc=B2*C2"
→ Excel cells get: =B2*C2 (copied to all rows)

# Aggregate parameter
"TotalFuel=A1111+A0611"

# Logical operation
"PassFail=IF(A1111>100,\"PASS\",\"FAIL\")"
```

**Success-Gating**:
- `params.txt` is updated ONLY after workbook saves successfully
- If workbook save fails, params.txt remains unchanged
- Ensures data consistency

**Example**:
```python
for update in retroactive_parameter_update(
    "FuelSumL",
    "lookup/paths.xlsx",
    "lookup/params.txt",
    "master.xlsx"
):
    print(f"{update['progress']}%: {update['message']}")
    # Output:
    # 1%: Initializing parameter update...
    # 50%: Expanding table boundaries...
    # 100%: Parameter 'FuelSumL' successfully added.
```

---

#### **E. Helper Functions**

##### `_normalize_date_key(value) → str`

Converts any date format to normalized ISO format for robust matching.

**Input Examples**: `"1/15/2024"`, `"2024-01-15"`, `"15 Jan 2024"`, `"Jan 15, 2024"`

**Output**: `"2024-01-15 12:34:56"` (or empty string if unparseable)

**Used By**: `ingest_new_runs`, `retroactive_parameter_update` for uniqueness matching

---

##### `_clean_value(raw_val) → Union[int, float, str, None]`

Sanitizes parameter values for Excel storage.

**Transformations**:
- Remove commas: `"1,234.5"` → `1234.5`
- Convert integers: `"42.0"` → `42`
- Preserve text: `"PASS"` → `"PASS"`
- Handle null: `NaN`, `"None"`, `""` → `None`

---

##### `_find_header_index(header_map, aliases) → int`

Finds column index using flexible alias matching.

**Parameters**:
- `header_map`: Dict from Excel `{column_name: index}`
- `aliases`: List of possible column names to search

**Returns**: Column index (1-indexed), or None if not found

**Example**:
```python
header_map = {"Date_Tested": 2, "Engine": 1, "Perf. Point": 3}
idx = _find_header_index(header_map, ["Date Tested", "Date", "Date_Tested"])
# Returns: 2
```

---

##### `_expand_excel_table(ws)`

Expands Excel ListObject bounds after adding rows/columns.

**Purpose**: Keeps table formatting and formulas synchronized with new data

**Called By**: End of `ingest_new_runs` and `retroactive_parameter_update`

---

##### `_create_backup(filepath) → str`

Creates timestamped backup of Excel file, retaining only 2 most recent.

**Returns**: Path to new backup file

**Example**:
```
master.xlsx → master.xlsx.20240622_143045.bak
           → master.xlsx.20240621_091523.bak (older backups deleted)
```

---

##### `_get_windows_user() → str`

Returns active Windows username (best-effort resolution).

**Priority Order**:
1. `os.environ["USERNAME"]`
2. `os.environ["USER"]`
3. `getpass.getuser()`
4. Fallback: `"unknown"`

---

##### `_extract_latest_test_date(run_path) → str`

Extracts the latest (most recent) test date from a file.

**Returns**: ISO format date string, or empty string if not found

**Used By**: `add_path_registry_entry` to populate Date_Tested field

---

---

## Access Backend (loopup_access.py)

*Complete Access backend implementation with SQL-optimized operations.*

### Function Reference

#### **Database Initialization**

##### `get_connection(db_path=None) → pyodbc.Connection`

**Purpose**: Establish connection to Access database, creating it if needed.

**Parameters**:
- `db_path` (str, optional): Custom database path. Defaults to lookup/lookup.accdb

**Returns**: Active ODBC connection object

**Auto-Creates**: Database file and schema if missing

**Example**:
```python
conn = get_connection()
cursor = conn.cursor()
```

---

#### **Paths Registry Operations**

##### `add_path_registry_entry(new_path, db_path=None, added_by=None, engine_name=None) → dict`

**Purpose**: Add path to Access database (mirrors Excel version).

**Returns**: Success/error dict matching Excel API

**Differences from Excel Version**:
- Inserts into `paths_registry` table instead of CSV/xlsx
- Atomic transaction (all-or-nothing)
- Faster for large registries

---

##### `get_latest_paths(limit=100, db_path=None) → list[dict]`

**Purpose**: Retrieve latest paths from database.

**SQL Query**:
```sql
SELECT path, engine, date_tested, date_added, added_by
FROM paths_registry
ORDER BY date_added DESC
LIMIT 100
```

---

#### **Master Data Operations**

##### `ingest_master_data(date_tested, engine, perf_point, param_values, db_path=None) → dict`

**Purpose**: Insert a row into master data with parameters (atomic operation).

**Parameters**:
- `date_tested`: Test date (normalized internally)
- `engine`: Engine name
- `perf_point`: Performance test value
- `param_values`: Dict of `{param_name: value}`
- `db_path`: Optional custom database path

**Returns**:
```python
# Success:
{"ok": True, "message": "Row inserted.", "id": 42}

# Duplicate date (silently skipped):
{"ok": False, "message": "Duplicate date_tested; skipped.", "skipped": True}

# Error:
{"ok": False, "message": "Error inserting data: ..."}
```

**Uniqueness Guarantee**: `date_tested` UNIQUE constraint at database level

**Parameter Storage**:
- Inserts to `master_data` table: (engine, date_tested, perf_point)
- Inserts to `parameter_values` join table: (master_data_id, param_name, value)
- All within single transaction

---

##### `get_master_data_by_date(date_tested, db_path=None) → dict`

**Purpose**: Retrieve complete row (with parameters) by date.

**Returns**:
```python
{
    "id": 42,
    "engine": "B737_Classic",
    "perf_point": "Take_B3",
    "params": {
        "A01111": 123,
        "A1_Power": 456.7,
        "FuelSumL": None
    }
}
```

---

##### `clear_master_data(db_path=None) → dict`

**Purpose**: Delete all master data (used for rescan workflow).

**SQL Operations**:
```sql
DELETE FROM parameter_values;
DELETE FROM master_data;
```

**Returns**: Success/error dict

---

#### **Parameters Operations**

##### `add_parameter(param_name, param_value=None, is_formula=False, db_path=None) → dict`

**Purpose**: Add parameter to `parameters` table.

**Parameters**:
- `param_name`: Parameter name (must be unique)
- `param_value`: Optional formula or value
- `is_formula`: Boolean flag for formula identification

**Example**:
```python
add_parameter("CustomCalc", param_value="=B2*C2", is_formula=True)
add_parameter("FuelSumL", is_formula=False)
```

---

##### `get_all_parameters(db_path=None) → list[str]`

**Purpose**: Get all parameter names from database.

**SQL Query**:
```sql
SELECT param_name FROM parameters ORDER BY param_name
```

---

---

## Integration Layer (loopup_sql_adapter.py)

Provides backward-compatible wrapper functions maintaining Excel API while routing to Access backend.

### Key Adapter Functions

#### `read_paths_registry(paths_registry=None, latest_first=True) → DataFrame`

- Internally calls `get_latest_paths()` from Access backend
- Returns DataFrame (same format as Excel version)
- `paths_registry` parameter ignored (uses database instead)

#### `ingest_new_runs(new_runs, all_params, master_excel, engine_overrides=None)`

- Generator wrapper around Access `ingest_master_data()`
- Maintains same progress update format
- Same logic for file parsing and parameter extraction
- Uses database transactions instead of Excel

#### `retroactive_parameter_update(new_param_str, paths_excel, params_txt, master_excel)`

- Wrapper around Access parameter management
- Same formula injection capabilities
- Success-gates database commits

---

## Data Flow Diagrams

### Ingestion Flow

```
┌─────────────────────┐
│  new_runs: [paths]  │
└──────────┬──────────┘
           │
    ┌──────▼──────┐
    │ For each    │
    │ test file   │
    └──────┬──────┘
           │
    ┌──────▼─────────────────┐
    │ load_raw_grid(path)    │
    │ Get DataFrame          │
    └──────┬─────────────────┘
           │
    ┌──────▼──────────────────┐
    │ _get_lookup_coords()    │
    │ Detect engine_row,      │
    │ test_row, date_row      │
    └──────┬──────────────────┘
           │
    ┌──────▼─────────────────────────┐
    │ Extract engine                  │
    │ (or use override/filename)      │
    └──────┬─────────────────────────┘
           │
    ┌──────▼────────────────────┐
    │ For each test column      │
    │ (contains "Take")         │
    └──────┬────────────────────┘
           │
    ┌──────▼──────────────────────────┐
    │ Extract date_tested              │
    │ Check uniqueness                │
    │ (Skip if duplicate)             │
    └──────┬──────────────────────────┘
           │
    ┌──────▼─────────────────┐
    │ For each parameter     │
    │ in column A            │
    └──────┬─────────────────┘
           │
    ┌──────▼──────────────────────┐
    │ Extract value               │
    │ _clean_value()             │
    └──────┬──────────────────────┘
           │
    ┌──────▼──────────────────────┐
    │ Write to:                    │
    │ - master.xlsx (Excel)        │
    │ - master_data table (Access) │
    └──────────────────────────────┘
```

### Parameter Addition Flow

```
┌────────────────┐
│ new_param_str  │ (e.g., "FuelSumL=A1111+A0611")
└────────┬───────┘
         │
    ┌────▼────────────────┐
    │ Extract header      │
    │ (before "=")        │
    └────┬────────────────┘
         │
    ┌────▼──────────────────┐
    │ Check if exists in    │
    │ params.txt or DB      │
    │ Abort if duplicate    │
    └────┬──────────────────┘
         │
    ┌────▼──────────────┐
    │ Has formula (=)?   │
    └────┬───────┬──────┘
         │       │
    ┌────▼─┐  ┌──▼──────────────────┐
    │ YES  │  │ NO                   │
    └────┬─┘  └──┬───────────────────┘
         │       │
    ┌────▼───────▼──────────────────┐
    │ Inject formula to all rows     │
    │ OR Retroactively populate      │
    │ from all registry files        │
    └────┬───────────────────────────┘
         │
    ┌────▼──────────────────┐
    │ Add column to master   │
    │ .xlsx (Excel) or       │
    │ parameter table        │
    │ (Access)               │
    └────┬──────────────────┘
         │
    ┌────▼──────────────────┐
    │ Save workbook/commit   │
    │ database               │
    └────┬──────────────────┘
         │
    ┌────▼──────────────────┐
    │ SUCCESS GATE:          │
    │ Only on success →      │
    │ Append to params.txt   │
    │ or DB parameters table │
    └───────────────────────┘
```

---

## Common Workflows

### Workflow 1: Add a Single Test File

```python
from lookup import add_path_registry_entry, preview_run_file

# Step 1: Preview file (optional but recommended)
preview = preview_run_file("C:/data/test_new.txt")
print(f"Engine: {preview['engine']} (detected: {preview['engine_detected']})")
print(f"Tests found: {len(preview['take_tests'])}")

# Step 2: Add to registry
result = add_path_registry_entry(
    "C:/data/test_new.txt",
    engine_name="B737_Classic" if not preview['engine_detected'] else None
)
if result['ok']:
    print("✓ Added to registry")
else:
    print(f"✗ Error: {result['message']}")
```

### Workflow 2: Ingest All Registry Files

```python
from lookup import read_paths_registry, ingest_new_runs, _load_all_params

# Step 1: Get all registered paths
df = read_paths_registry()
paths = df['Path'].tolist()

# Step 2: Load parameters
all_params = _load_all_params()

# Step 3: Ingest
for update in ingest_new_runs(paths, all_params, "master.xlsx"):
    print(f"{update['progress']}/{update['total']}: {update['message']}")
```

### Workflow 3: Add New Parameter (Non-Formula)

```python
from lookup import retroactive_parameter_update

# Add parameter and populate from all files
for update in retroactive_parameter_update(
    "NewParam",
    "lookup/paths.xlsx",
    "lookup/params.txt",
    "master.xlsx"
):
    if update['progress'] == 100:
        print("✓ Parameter added and populated")
```

### Workflow 4: Add Calculated Parameter (Formula)

```python
# Formula parameters are injected to all rows
for update in retroactive_parameter_update(
    "TotalFuel=A1111+A0611",  # Excel formula
    "lookup/paths.xlsx",
    "lookup/params.txt",
    "master.xlsx"
):
    if update['progress'] == 100:
        print("✓ Formula injected to all rows")
```

### Workflow 5: Switch to Access Backend

```bash
# Set environment variable
set LOOKUP_BACKEND=access

# Run application
python app.py

# Database created automatically at: lookup/lookup.accdb
```

---

## Modification Manual

### Adding a New Parameter Type

**Scenario**: You need to track a new measurement type.

**Steps**:

1. **Update params.txt**:
   ```
   A01111
   A01112
   NewParamType
   ```

2. **Add to Master Header** (Excel):
   - Manually add column header: `NewParamType`

3. **Populate Retroactively**:
   ```python
   from lookup import retroactive_parameter_update
   
   for update in retroactive_parameter_update(
       "NewParamType",
       "lookup/paths.xlsx",
       "lookup/params.txt",
       "master.xlsx"
   ):
       print(update['message'])
   ```

---

### Modifying Date Detection

**Scenario**: Your files use a different date format that's not being detected.

**Location**: `_get_lookup_coords()` function

**Current Logic**:
1. Scans first 8 rows for "Take" keyword
2. Row with most hits = test_row
3. Date row = test_row + 1

**To Modify**:
```python
# Find this section:
for r_idx in range(max_scan_rows):
    take_hits = 0
    for c_idx in range(2, len(df.columns)):
        raw_val = df.iloc[r_idx, c_idx]
        if pd.isna(raw_val):
            continue
        if KEYWORD_Y.lower() in str(raw_val).lower():  # ← Change "Take" keyword here
            take_hits += 1

# Example: If files use "Takeoff" instead of "Take":
KEYWORD_Y = "Takeoff"  # Change at top of file
```

---

### Modifying Column Name Matching

**Scenario**: Registry uses different column names.

**Location**: `_normalize_paths_df()` function

**Current Mapping**:
```python
if compact in {"path", "file_path"}:
    rename_map[col] = "Path"
```

**To Add Support for "FilePath"**:
```python
if compact in {"path", "file_path", "filepath"}:  # ← Add here
    rename_map[col] = "Path"
```

---

### Adding Parameters to SQL Backend

**Scenario**: You've added new parameters but they're not in database.

**Solution**:

```python
from lookup.loopup_access import add_parameter

# Manually add parameter to database
add_parameter("NewParam1")
add_parameter("NewParam2")
add_parameter("FormulaParam", param_value="=A1+B1", is_formula=True)

# Verify
from lookup.loopup_access import get_all_parameters
print(get_all_parameters())
```

---

### Customizing Data Cleaning

**Scenario**: Your parameter values need custom transformation.

**Location**: `_clean_value()` function

**Current Transformations**:
- Remove commas
- Convert to numeric
- Handle null values

**To Add Percentage Conversion**:
```python
def _clean_value(raw_val):
    """Handles commas, percentages, and numeric conversions."""
    if pd.isna(raw_val): 
        return None
    val_str = str(raw_val).strip()
    if val_str.lower() in ["nan", "none", ""]: 
        return None
    
    # NEW: Handle percentages
    if val_str.endswith("%"):
        val_str = val_str[:-1].strip()
        try:
            return float(val_str) / 100
        except ValueError:
            pass
    
    val_str = val_str.replace(',', '.')
    try:
        numeric_val = float(val_str)
        return int(numeric_val) if numeric_val.is_integer() else numeric_val
    except ValueError: 
        return val_str
```

---

### Extending Ingestion with Custom Logic

**Scenario**: You need to validate or transform data during ingestion.

**Location**: `ingest_new_runs()` generator, after value extraction

**Current Code**:
```python
raw_data_val = df.iloc[param_row, data_col]
ws.cell(row=2, column=target_col_idx, value=_clean_value(raw_data_val))
```

**To Add Validation**:
```python
raw_data_val = df.iloc[param_row, data_col]
cleaned = _clean_value(raw_data_val)

# NEW: Validate value before write
if param_name == "A1_Power" and isinstance(cleaned, (int, float)):
    if cleaned < 0 or cleaned > 1000:  # Out of range check
        yield {
            "progress": current_step,
            "total": total_steps,
            "message": f"Warning: {param_name} value {cleaned} out of range"
        }
        cleaned = None  # Skip invalid value

ws.cell(row=2, column=target_col_idx, value=cleaned)
```

---

---

## Troubleshooting

### Issue: Duplicate Dates Not Being Skipped

**Symptom**: Same test date appears multiple times in master.xlsx

**Root Causes**:
1. Date normalization failed (different formats not recognized)
2. Date column not detected correctly

**Diagnosis**:
```python
from lookup import _normalize_date_key

# Test normalization
key1 = _normalize_date_key("01/15/2024")
key2 = _normalize_date_key("2024-01-15")
print(f"Key1: {key1}")
print(f"Key2: {key2}")
print(f"Match: {key1 == key2}")  # Should be True
```

**Solution**:
- Check `_get_lookup_coords()` is detecting date_row correctly
- Use `preview_run_file()` to verify date extraction
- Manually specify date column in retroactive update

---

### Issue: Engine Not Detected, But File Has Engine Row

**Symptom**: `preview_run_file()` returns `engine_detected=False` for valid engine

**Root Cause**: Engine value doesn't match any of the valid patterns

**Check**:
- Engine contains "Take" keyword → interpreted as invalid
- Engine is "unknown" or empty
- Engine starts with "#"

**Solution**:
```python
# Always use engine_name override if auto-detection fails
result = add_path_registry_entry(
    filepath,
    engine_name="B737_Classic"  # Override
)
```

---

### Issue: Parameters Not Populating in Retroactive Update

**Symptom**: Retroactive parameter added to master, but cells are empty

**Root Causes**:
1. Parameter not found in file (column A)
2. Date matching failed (dates don't normalize the same)
3. No "Take" test columns detected in file

**Diagnosis**:
```python
from lookup import preview_run_file

preview = preview_run_file("C:/data/test.txt")
print(f"Tests found: {preview['take_tests']}")  # Should not be empty
print(f"Dates: {preview['tested_dates']}")
```

**Solution**:
- Verify parameter name matches exactly (case-sensitive)
- Check file has "Take" keyword in test row
- Manually populate cells if needed

---

### Issue: "Date not found" Error

**Symptom**: Date column not automatically detected in retroactive update

**Root Cause**: Date column has non-standard header name

**Solution**:
1. Manually rename column to one of the recognized aliases:
   - `Date_Tested`, `Date Tested`, `Date`, `Full_date`

2. Or modify header matching in `retroactive_parameter_update()`:
   ```python
   preferred_date_keys = [
       "date_tested",
       "your_custom_name_here",  # ← Add here
       "date_test",
   ]
   ```

---

### Issue: Performance Slow on Large Files

**Symptom**: Ingestion takes a long time

**Solution**:
- Switch to Access backend for 10x faster queries:
  ```bash
  set LOOKUP_BACKEND=access
  python app.py
  ```

---

### Issue: Access Database Driver Not Found

**Symptom**: Error message about "Microsoft Access Driver"

**Solution** (Windows):
1. Install Microsoft Access Database Engine:
   - Download from Microsoft
   - Or install Office with Access

2. Fallback to Excel backend:
   ```bash
   set LOOKUP_BACKEND=excel
   python app.py
   ```

---

## Best Practices

1. **Always preview before ingesting**: Use `preview_run_file()` to verify file structure
2. **Backup before changes**: Function automatically creates backups, but keep external copies
3. **Use normalized dates**: Let `_normalize_date_key()` handle date matching
4. **Test with small datasets first**: Before processing large file lists
5. **Success-gate writes**: Retroactive updates only commit on successful completion
6. **Document custom parameters**: Update params.txt comments if needed
7. **Use Access for production**: Better performance and data integrity for large datasets

---

## Summary Table

| Task | Function | Location |
|------|----------|----------|
| Load file | `load_raw_grid()` | loopup.py |
| Detect coordinates | `_get_lookup_coords()` | loopup.py |
| Preview file | `preview_run_file()` | loopup.py |
| Add path to registry | `add_path_registry_entry()` | loopup.py / loopup_access.py |
| Read registry | `read_paths_registry()` | loopup.py / loopup_sql_adapter.py |
| Ingest files | `ingest_new_runs()` | loopup.py / loopup_sql_adapter.py |
| Add parameter | `retroactive_parameter_update()` | loopup.py / loopup_sql_adapter.py |
| Normalize date | `_normalize_date_key()` | loopup.py |
| Clean value | `_clean_value()` | loopup.py |
| Access database | `get_connection()` | loopup_access.py |
| Query parameters | `get_all_parameters()` | loopup_access.py |
| Get master by date | `get_master_data_by_date()` | loopup_access.py |

---

**Document End**
