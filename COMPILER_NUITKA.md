# Nuitka Build Profile (Network Drive Optimized)

This project now uses Nuitka as the preferred compiler profile for faster startup than PyInstaller when launching from a network share.

## Why this profile

- Uses true compilation (Nuitka) instead of pure freezing.
- Builds a single-file executable (`--onefile`) to reduce many small network reads.
- Extracts runtime payload to local cache (`%LOCALAPPDATA%\\CFM56GraphDash\\nuitka_cache`) so imported modules and binaries are loaded from local storage after launch.
- Includes explicit hidden imports and package/data bundles needed by Dash page discovery and Access DB support.

## Build

From project root:

```powershell
.\build_nuitka.ps1
```

Or:

```bat
build_nuitka.bat
```

## Output

Build artifacts are written to:

- `build\app.dist\` (intermediate)
- `build\app.exe` (onefile executable)

## Included hidden imports/modules

- `compiler_explicit_imports` (explicit Dash + Flask import surface)
- `pages.home`
- `pages.graph`
- `pages.editor`
- `pages.table`
- `pages.singlegraph`
- `lookup`
- `lookup.lookup`
- `lookup.loopup` (compatibility alias)
- `functions`
- `baselines`
- `pyodbc`

## Included data

- `config.json`
- `assets\`
- `pages\`
- `lookup\`

## Explicit runtime import shim

- `compiler_explicit_imports.py` is imported from startup to make Dash tools/add-ons and Flask backend imports explicit for static analysis during compile.

## Notes

- Access DB still requires a compatible Microsoft Access ODBC driver installed on target machines.
- If your environment blocks local execution entirely, keep running the executable from the network drive; the local onefile cache still reduces repeated module I/O overhead.
- To test startup impact, run the generated executable twice and compare second-launch time.
