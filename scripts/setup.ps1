<#
.SYNOPSIS
    Sets up the poc_bi_tool Python environment on Windows.

.DESCRIPTION
    Checks for a usable Python, creates a .venv in the repo root, installs
    requirements.txt into it, and runs the data health check.

    Safe to re-run: an existing .venv is reused unless -Force is passed.

.PARAMETER Force
    Delete and recreate the virtual environment from scratch.

.PARAMETER SkipVerify
    Skip the data health check at the end.

.EXAMPLE
    .\scripts\setup.ps1

.EXAMPLE
    .\scripts\setup.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$SkipVerify
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

Write-Host "poc_bi_tool - Windows setup" -ForegroundColor White
Write-Host "repo: $RepoRoot"

# --- 1. Find a usable Python -------------------------------------------------
Write-Step 'Locating Python'

# The "py" launcher ships with python.org installs and picks the newest
# version, so prefer it over whatever "python" happens to be on PATH - on a
# stock Windows box that is often the Store stub, which does nothing useful.
$pythonExe = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = 'py'
    $pythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = 'python'
} else {
    throw @'
No Python found on PATH.

Install Python 3.10 or newer, then re-run this script:
  winget install Python.Python.3.12
or download from https://www.python.org/downloads/windows/
(tick "Add python.exe to PATH" in the installer).

Then open a NEW terminal so the updated PATH is picked up.
'@
}

# 2>&1 can hand back an ErrorRecord or an array of lines - flatten to a string
# so the regex below behaves.
$versionText = (& $pythonExe @pythonArgs --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to run Python ($versionText). If this opened the Microsoft Store, disable the Python App Execution Aliases in Settings > Apps > Advanced app settings > App execution aliases."
}

# "Python 3.12.4" -> 3.12
if ($versionText -notmatch 'Python (\d+)\.(\d+)') {
    throw "Could not read a version number from: $versionText"
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    throw "Found $versionText but this project needs Python 3.10 or newer."
}
Write-Ok "$versionText"

# --- 2. Create the virtual environment --------------------------------------
Write-Step 'Preparing virtual environment'

if ($Force -and (Test-Path $VenvDir)) {
    Write-Warn 'Removing existing .venv (-Force)'
    Remove-Item -Recurse -Force $VenvDir
}

if (Test-Path $VenvPython) {
    Write-Ok 'Reusing existing .venv (pass -Force to rebuild)'
} else {
    & $pythonExe @pythonArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
    Write-Ok "Created $VenvDir"
}

if (-not (Test-Path $VenvPython)) {
    throw "Expected $VenvPython to exist but it does not - the venv is incomplete."
}

# --- 3. Install dependencies -------------------------------------------------
Write-Step 'Installing dependencies'

& $VenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }

& $VenvPython -m pip install -r (Join-Path $RepoRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed.' }
Write-Ok 'requirements.txt installed'

# --- 4. Verify ---------------------------------------------------------------
if (-not $SkipVerify) {
    Write-Step 'Running tests'
    & $VenvPython -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed (see above).' }

    Write-Step 'Running data health check'
    & $VenvPython (Join-Path $RepoRoot 'scripts\verify_data.py')
    if ($LASTEXITCODE -ne 0) {
        throw 'Data health check reported errors (see above).'
    }
}

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host @"

Launch the dashboard:
    .\.venv\Scripts\streamlit.exe run app.py

Or activate the environment first, then use the tools directly:
    .\.venv\Scripts\Activate.ps1
    streamlit run app.py
    pytest
    python scripts\export_clean.py

If PowerShell blocks activation with "running scripts is disabled", allow
local scripts for your user once:
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
"@
