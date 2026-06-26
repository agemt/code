$ErrorActionPreference = "Stop"

$pythonExe = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $projectRoot
try {
    Write-Host "Installing compiler requirements from requirements-build.txt..."
    & $pythonExe -m pip install --upgrade -r requirements-build.txt

    $nuitkaArgs = @(
        "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--assume-yes-for-downloads",
        "--python-flag=no_site",
        "--output-dir=build",
        "--remove-output",
        "--windows-console-mode=disable",
        "--onefile-tempdir-spec=%LOCALAPPDATA%\\CFM56GraphDash\\nuitka_cache",

        "--include-data-files=config.json=config.json",
        "--include-data-dir=assets=assets",
        "--include-data-dir=pages=pages",
        "--include-data-dir=lookup=lookup",

        "--include-module=baselines",
        "--include-module=compiler_explicit_imports",
        "--include-module=functions",
        "--include-module=lookup",
        "--include-module=lookup.lookup",
        "--include-module=lookup.loopup",
        "--include-module=pages.home",
        "--include-module=pages.graph",
        "--include-module=pages.editor",
        "--include-module=pages.table",
        "--include-module=pages.singlegraph",
        "--include-module=pyodbc",

        "--include-package=dash",
        "--include-package=dash_bootstrap_components",
        "--include-package=dash_mantine_components",
        "--include-package=dash_ag_grid",
        "--include-package=flask",
        "--include-package=werkzeug",
        "--include-package=jinja2",
        "--include-package=plotly",

        "app.py"
    )

    Write-Host "Compiling with Nuitka..."
    & $pythonExe @nuitkaArgs

    Write-Host "Build complete. Output is under build/."
}
finally {
    Pop-Location
}
