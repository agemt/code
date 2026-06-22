# Database Backend Migration Guide

## Current Status

The lookup system now supports two backends:

1. **Excel** (default/legacy) - Original implementation using Excel files and CSV
2. **Access** (optimized) - New SQL-based implementation for better matching and performance

## Switching Backends

### To use Access backend:

```bash
# Set environment variable before running app
set LOOKUP_BACKEND=access
python app.py
```

Or in PowerShell:
```powershell
$env:LOOKUP_BACKEND = "access"
python app.py
```

Or add to `.env` file (if using python-dotenv):
```
LOOKUP_BACKEND=access
```

### To use Excel backend (default):

```bash
python app.py
```

Or explicitly:
```bash
set LOOKUP_BACKEND=excel
python app.py
```

## Benefits of Access Backend

1. **SQL-Based Matching**: Efficient date-based uniqueness checks
2. **Better Performance**: Optimized queries for large datasets
3. **Atomic Operations**: Transactional consistency
4. **Flexible Queries**: Can extend with complex SQL operations
5. **No File Locking**: Access database handles concurrency better

## Migration Steps

1. **Test locally** with small dataset:
   ```bash
   set LOOKUP_BACKEND=access
   python app.py
   ```

2. **Add files** and verify ingestion works:
   - Use "Add File" workflow
   - Verify data appears in "Latest Paths" table
   - Check database file created at: `lookup/lookup.accdb`

3. **Test retroactive parameters**:
   - Add a parameter via "Add Parameter"
   - Run "Rescan All Paths" to populate values

4. **Verify data integrity**:
   - Compare database results with expected outcomes
   - Check duplicate-date handling (should be silently skipped)

5. **Switch permanently**:
   - Set LOOKUP_BACKEND=access in deployment environment
   - Keep Excel files as backup if needed

## Database Schema

### paths_registry
- id: Auto-increment primary key
- path: TEXT UNIQUE
- engine: TEXT
- date_tested: DATETIME
- date_added: DATETIME (default NOW())
- added_by: TEXT

### master_data
- id: Auto-increment primary key
- engine: TEXT
- date_tested: DATETIME UNIQUE
- perf_point: TEXT
- created_at: DATETIME (default NOW())

### parameters
- id: Auto-increment primary key
- param_name: TEXT UNIQUE
- param_value: TEXT
- is_formula: BIT (0 or 1)

### parameter_values
- id: Auto-increment primary key
- master_data_id: INTEGER (FK to master_data)
- param_name: TEXT
- value: TEXT

## Troubleshooting

**"Driver not found" error:**
- Ensure Microsoft Access Driver for .mdb/.accdb is installed
- Windows typically includes this, but may need to enable it

**Database locked error:**
- Access only locks during active operations
- Close app and try again
- Check for stale processes

**Data not appearing:**
- Verify database file exists: `lookup/lookup.accdb`
- Check app logs for errors
- Fall back to Excel backend for comparison

## Rollback

If issues occur, simply switch back to Excel:
```bash
set LOOKUP_BACKEND=excel
python app.py
```

Excel data remains unchanged and can be used immediately.
