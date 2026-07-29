<#
.SYNOPSIS
    Start a Claude Code Remote Control session you can drive from your phone.

.DESCRIPTION
    Runs Claude Code in server mode on this machine and keeps the machine
    awake for as long as it runs. Code execution, filesystem access, SSH keys,
    VPN routes and MCP servers all stay local - your phone is only the
    steering wheel.

    Why the keep-awake matters: Remote Control is a local process. If Windows
    sleeps, the process stops and the session ends. If the machine is awake
    but offline for roughly 10 minutes the session also times out. This script
    holds a system-required lock (the same mechanism a video player uses) and
    releases it when you stop.

    The display is still allowed to sleep - only the system is held awake.

.PARAMETER Name
    Session title shown in the Claude app. Defaults to the repo folder name.

.PARAMETER Continue
    Resume the most recent Remote Control session from this directory instead
    of creating a new one. Requires Claude Code 2.1.200+.

.PARAMETER Worktree
    Give each on-demand session its own git worktree, so parallel sessions
    cannot fight over the same files.

.PARAMETER AllowSleep
    Do not hold the machine awake. Only sensible if you have already changed
    the power plan yourself.

.EXAMPLE
    .\scripts\start_remote_control.ps1

.EXAMPLE
    .\scripts\start_remote_control.ps1 -Name "BI tool" -Worktree
#>
[CmdletBinding()]
param(
    [string]$Name,
    [switch]$Continue,
    [switch]$Worktree,
    [switch]$AllowSleep
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Name) { $Name = Split-Path -Leaf $RepoRoot }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw "Claude Code is not installed or not on PATH. Run .\scripts\setup_claude_code.ps1 first, then open a new terminal."
}

# Fail fast on the variables that make Remote Control refuse to start, rather
# than letting it fail with a message about your account.
foreach ($v in 'ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'DISABLE_TELEMETRY',
                'DO_NOT_TRACK', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC',
                'DISABLE_GROWTHBOOK', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX') {
    if (Get-Item "Env:\$v" -ErrorAction SilentlyContinue) {
        throw "$v is set, which disables Remote Control. Run .\scripts\setup_claude_code.ps1 -Fix"
    }
}
if ($env:ANTHROPIC_BASE_URL -and $env:ANTHROPIC_BASE_URL -notmatch 'api\.anthropic\.com') {
    throw "ANTHROPIC_BASE_URL points at $env:ANTHROPIC_BASE_URL. Remote Control requires api.anthropic.com."
}

# SetThreadExecutionState tells Windows this thread is doing work that must not
# be interrupted by sleep. ES_CONTINUOUS makes it persist until cleared, and it
# is scoped to this thread - so it lasts exactly as long as this script blocks
# on the claude process, and dies with it even if the script is killed.
if (-not $AllowSleep) {
    Add-Type -Name Power -Namespace Win32 -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
    # Numeric literals, not strings: PowerShell does not reliably parse a
    # quoted "0x..." into an integer type.
    $ES_CONTINUOUS      = [uint32]0x80000000
    $ES_SYSTEM_REQUIRED = [uint32]0x00000001
    $previous = [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    if ($previous -eq 0) {
        Write-Host 'Warning: could not hold the machine awake; it may sleep and end the session.' -ForegroundColor Yellow
    } else {
        Write-Host 'Holding this machine awake until you stop the session (display may still sleep).' -ForegroundColor DarkGray
    }
}

$claudeArgs = @('remote-control', '--name', $Name)
if ($Continue) { $claudeArgs += '--continue' }
if ($Worktree) { $claudeArgs += @('--spawn', 'worktree') }

Write-Host ''
Write-Host "Starting Remote Control session '$Name'" -ForegroundColor Cyan
Write-Host "  working directory: $RepoRoot"
Write-Host ''
Write-Host '  Press SPACE in this window to show a QR code for your phone.' -ForegroundColor DarkGray
Write-Host '  Or open the Claude app -> Code tab and pick the session by name.' -ForegroundColor DarkGray
Write-Host '  Keep this window open: closing it ends the session.' -ForegroundColor DarkGray
Write-Host ''

$exit = 0
try {
    Push-Location $RepoRoot
    & claude @claudeArgs
    $exit = $LASTEXITCODE
} finally {
    Pop-Location
    if (-not $AllowSleep) {
        # ES_CONTINUOUS alone clears the system-required request, so normal
        # power management resumes.
        [void][Win32.Power]::SetThreadExecutionState([uint32]0x80000000)
        Write-Host 'Released the keep-awake lock.' -ForegroundColor DarkGray
    }
}

if ($exit -ne 0) {
    Write-Host ''
    Write-Host "claude exited with code $exit." -ForegroundColor Yellow
    Write-Host 'If it mentions your account or organization, see the troubleshooting'
    Write-Host 'table in docs\mobile-remote-control.md.'
}

exit $exit
