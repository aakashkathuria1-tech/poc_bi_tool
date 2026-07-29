<#
.SYNOPSIS
    One-time setup of Claude Code on this Windows machine, ready for Remote
    Control from the Claude mobile app.

.DESCRIPTION
    Installs Claude Code (and Git for Windows, which enables the Bash tool),
    then preflights the conditions Remote Control actually requires - the
    environment variables that silently disable it are the usual reason it
    "just doesn't work".

    Safe to re-run. It installs what is missing and reports what is already
    in place.

    After this finishes you still have to sign in once interactively:
        claude
        /login

.PARAMETER SkipGit
    Do not install Git for Windows. Claude Code falls back to the PowerShell
    tool for shell commands.

.PARAMETER Fix
    Clear the user-scoped environment variables that block Remote Control,
    instead of only reporting them.

.EXAMPLE
    .\scripts\setup_claude_code.ps1

.EXAMPLE
    .\scripts\setup_claude_code.ps1 -Fix
#>
[CmdletBinding()]
param(
    [switch]$SkipGit,
    [switch]$Fix
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    [OK]   $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Bad($msg)  { Write-Host "    [FAIL] $msg" -ForegroundColor Red }

$problems = [System.Collections.Generic.List[string]]::new()

Write-Host "Claude Code - Windows setup for mobile Remote Control" -ForegroundColor White

# --- 1. Windows version ------------------------------------------------------
Write-Step 'Checking Windows version'
$build = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
if ($build -lt 17763) {
    throw "Claude Code needs Windows 10 1809+ (build 17763) or Server 2019+. This is build $build."
}
Write-Ok "build $build"

# --- 2. Claude Code ----------------------------------------------------------
Write-Step 'Installing Claude Code'
if (Get-Command claude -ErrorAction SilentlyContinue) {
    $ver = (& claude --version 2>&1 | Out-String).Trim()
    Write-Ok "already installed: $ver"
} else {
    # Official native installer. Auto-updates in the background afterwards.
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression

    # The installer adds ~\.local\bin to PATH, but this process started before
    # that, so refresh PATH in-session rather than making the user reopen it.
    $userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $env:Path    = "$machinePath;$userPath"

    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        throw "Claude Code installed but 'claude' is still not on PATH. Open a new terminal and re-run this script."
    }
    Write-Ok ((& claude --version 2>&1 | Out-String).Trim())
}

# --- 3. Git for Windows ------------------------------------------------------
Write-Step 'Checking Git for Windows'
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Ok ((& git --version 2>&1 | Out-String).Trim())
} elseif ($SkipGit) {
    Write-Warn2 'Git not installed (-SkipGit). Claude Code will use the PowerShell tool for shell commands.'
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host '    Installing Git for Windows (enables the Bash tool)...'
    & winget install --id Git.Git --silent --accept-source-agreements --accept-package-agreements
    Write-Ok 'Git installed - open a new terminal for it to appear on PATH'
} else {
    Write-Warn2 'winget not available. Install Git manually: https://git-scm.com/downloads/win'
}

# --- 4. Remote Control preflight --------------------------------------------
# These are the documented blockers. Each one disables Remote Control, and the
# resulting error messages point at the account rather than the variable, so
# check them explicitly.
Write-Step 'Preflighting Remote Control requirements'

$blockers = @(
    @{ Name = 'ANTHROPIC_API_KEY'
       Why  = 'Remote Control needs a claude.ai login, not an API key' }
    @{ Name = 'CLAUDE_CODE_OAUTH_TOKEN'
       Why  = 'setup-token credentials can only make model requests' }
    @{ Name = 'DISABLE_TELEMETRY'
       Why  = 'disables the feature-flag evaluation Remote Control depends on' }
    @{ Name = 'DO_NOT_TRACK'
       Why  = 'disables the feature-flag evaluation Remote Control depends on' }
    @{ Name = 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'
       Why  = 'disables the feature-flag evaluation Remote Control depends on' }
    @{ Name = 'DISABLE_GROWTHBOOK'
       Why  = 'disables the feature-flag evaluation Remote Control depends on' }
    @{ Name = 'CLAUDE_CODE_USE_BEDROCK'
       Why  = 'routes the session away from api.anthropic.com' }
    @{ Name = 'CLAUDE_CODE_USE_VERTEX'
       Why  = 'routes the session away from api.anthropic.com' }
)

foreach ($b in $blockers) {
    $name = $b.Name
    $inProcess = [Environment]::GetEnvironmentVariable($name, 'Process')
    $inUser    = [Environment]::GetEnvironmentVariable($name, 'User')
    $inMachine = [Environment]::GetEnvironmentVariable($name, 'Machine')

    if ($inProcess -or $inUser -or $inMachine) {
        $scopes = @()
        if ($inUser)    { $scopes += 'User' }
        if ($inMachine) { $scopes += 'Machine' }
        if ($inProcess -and -not $inUser -and -not $inMachine) { $scopes += 'Process' }

        if ($Fix -and $inUser) {
            [Environment]::SetEnvironmentVariable($name, $null, 'User')
            Remove-Item "Env:\$name" -ErrorAction SilentlyContinue
            Write-Ok "cleared $name (User scope)"
        } else {
            Write-Bad "$name is set [$($scopes -join ', ')] - $($b.Why)"
            if ($inMachine) {
                $problems.Add("$name is set machine-wide; clear it as Administrator")
            } else {
                $problems.Add("$name is set; re-run with -Fix to clear it")
            }
        }
    }
}

# ANTHROPIC_BASE_URL is only a problem when it points somewhere else.
$baseUrl = $env:ANTHROPIC_BASE_URL
if ($baseUrl -and $baseUrl -notmatch 'api\.anthropic\.com') {
    Write-Bad "ANTHROPIC_BASE_URL points at $baseUrl - Remote Control requires api.anthropic.com"
    $problems.Add('ANTHROPIC_BASE_URL points away from api.anthropic.com')
}

if ($problems.Count -eq 0) {
    Write-Ok 'no blocking environment variables found'
}

# --- 5. Diagnostics ----------------------------------------------------------
Write-Step 'Running claude doctor'
& claude doctor

# --- 6. Next steps -----------------------------------------------------------
Write-Host "`n$('=' * 66)" -ForegroundColor White

if ($problems.Count -gt 0) {
    Write-Host 'Setup finished with blockers to clear:' -ForegroundColor Yellow
    foreach ($p in $problems) { Write-Host "  - $p" -ForegroundColor Yellow }
    Write-Host ''
}

Write-Host @"
Next steps (one time):

  1. Sign in - Remote Control needs a claude.ai account, not an API key:
         claude
     then inside the session:
         /login
     Accept the workspace-trust prompt. Do this from THIS project directory:
     trust is never saved for your home directory.

  2. Install the Claude app on your phone. Inside a claude session run:
         /mobile
     and scan the QR code. Sign in with the SAME account.

  3. Turn on push notifications - inside a claude session:
         /config
     enable "Push when Claude decides" and "Push when actions required".

Then, every time you want to work from your phone:

     .\scripts\start_remote_control.ps1

Full guide: docs\mobile-remote-control.md
"@
Write-Host ('=' * 66) -ForegroundColor White
