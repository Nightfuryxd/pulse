# =============================================================================
# PULSE Universal Agent Installer — Windows
# Supports: Windows 10/11, Windows Server 2016+
# Run in an elevated PowerShell prompt:
#
#   $env:PULSE_API_URL = "http://your-pulse-server:8000"
#   irm https://raw.githubusercontent.com/YOUR_ORG/pulse/main/install.ps1 | iex
#
# Or download and run:
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\install.ps1
# =============================================================================
param(
    [string]$PulseApiUrl     = $env:PULSE_API_URL     ?? "http://localhost:8000",
    [string]$NodeId          = $env:NODE_ID            ?? $env:COMPUTERNAME,
    [string]$CollectInterval = $env:COLLECT_INTERVAL   ?? "10",
    [string]$SnmpTargets     = $env:SNMP_TARGETS       ?? "",
    [string]$SshTargets      = $env:SSH_TARGETS        ?? "",
    [string]$InstallDir      = "C:\PulseAgent",
    [string]$ServiceName     = "PulseAgent",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host ""
    Write-Host "  ██████  ██    ██ ██      ███████ ███████" -ForegroundColor Cyan
    Write-Host "  ██   ██ ██    ██ ██      ██      ██     " -ForegroundColor Cyan
    Write-Host "  ██████  ██    ██ ██      ███████ █████  " -ForegroundColor Cyan
    Write-Host "  ██      ██    ██ ██           ██ ██     " -ForegroundColor Cyan
    Write-Host "  ██       ██████  ███████ ███████ ███████" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Universal Infrastructure Agent — Windows Installer" -ForegroundColor White
    Write-Host ""
}

function Log-Info  ($msg) { Write-Host "[PULSE] $msg"  -ForegroundColor Cyan }
function Log-OK    ($msg) { Write-Host "[OK]    $msg"  -ForegroundColor Green }
function Log-Warn  ($msg) { Write-Host "[WARN]  $msg"  -ForegroundColor Yellow }
function Log-Error ($msg) { Write-Host "[ERROR] $msg"  -ForegroundColor Red; exit 1 }

# ── Uninstall ────────────────────────────────────────────────────────────────
function Uninstall-Agent {
    Log-Info "Uninstalling PULSE agent..."
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Log-OK "Windows service '$ServiceName' removed"
    }
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
        Log-OK "Removed $InstallDir"
    }
    Log-OK "PULSE agent uninstalled"
    exit 0
}

# ── Check admin ──────────────────────────────────────────────────────────────
function Assert-Admin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Log-Error "Run this script as Administrator (right-click PowerShell → Run as Administrator)"
    }
}

# ── Check / install Python ────────────────────────────────────────────────────
function Assert-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $ver = & python --version 2>&1
        Log-Info "Found $ver"
        return
    }
    Log-Info "Python not found — installing via winget..."
    try {
        winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        Log-OK "Python installed"
    } catch {
        Log-Warn "winget failed. Download Python manually from https://python.org/downloads"
        Log-Error "Python 3.9+ is required"
    }
}

# ── Install agent files ───────────────────────────────────────────────────────
function Install-AgentFiles {
    Log-Info "Creating install directory: $InstallDir"
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    # Try to download collector.py from the PULSE API, then GitHub
    $collectorPath = Join-Path $InstallDir "collector.py"
    $downloaded = $false

    try {
        Invoke-WebRequest -Uri "$PulseApiUrl/agent/collector.py" -OutFile $collectorPath -TimeoutSec 10 -UseBasicParsing
        Log-OK "Downloaded collector.py from API"
        $downloaded = $true
    } catch {}

    if (-not $downloaded) {
        try {
            $ghUrl = "https://raw.githubusercontent.com/YOUR_ORG/pulse/main/agent/collector.py"
            Invoke-WebRequest -Uri $ghUrl -OutFile $collectorPath -TimeoutSec 15 -UseBasicParsing
            Log-OK "Downloaded collector.py from GitHub"
            $downloaded = $true
        } catch {}
    }

    if (-not $downloaded) {
        Log-Error "Cannot download collector.py — ensure PULSE_API_URL is reachable"
    }

    # Write .env file
    $envContent = @"
PULSE_API_URL=$PulseApiUrl
NODE_ID=$NodeId
COLLECT_INTERVAL=$CollectInterval
SNMP_TARGETS=$SnmpTargets
SSH_TARGETS=$SshTargets
"@
    Set-Content -Path (Join-Path $InstallDir ".env") -Value $envContent

    # Create virtualenv
    Log-Info "Creating Python virtual environment..."
    & python -m venv (Join-Path $InstallDir "venv")

    $pip = Join-Path $InstallDir "venv\Scripts\pip.exe"
    Log-Info "Installing dependencies..."
    & $pip install --quiet --upgrade pip
    & $pip install --quiet psutil httpx python-dotenv pyyaml "pysnmp==5.1.0"
    Log-OK "Dependencies installed"
}

# ── Create Windows wrapper ────────────────────────────────────────────────────
function Install-Wrapper {
    $wrapperPath = Join-Path $InstallDir "run_agent.cmd"
    Set-Content -Path $wrapperPath -Value @"
@echo off
cd /d "$InstallDir"
"$InstallDir\venv\Scripts\python.exe" "$InstallDir\collector.py"
"@
    $pythonPath = Join-Path $InstallDir "venv\Scripts\python.exe"
    return $pythonPath
}

# ── Register as Windows Service ──────────────────────────────────────────────
function Install-Service {
    param([string]$PythonPath)

    Log-Info "Registering Windows service: $ServiceName"

    # Remove existing service if present
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep 1
    }

    $binPath = "`"$PythonPath`" `"$InstallDir\collector.py`""

    # Use sc.exe to create the service
    sc.exe create $ServiceName `
        binPath= $binPath `
        DisplayName= "PULSE Infrastructure Agent" `
        start= auto `
        obj= LocalSystem | Out-Null

    sc.exe description $ServiceName "PULSE universal infrastructure monitoring agent" | Out-Null

    # Set environment variables for the service via registry
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
    $envVars = @(
        "PULSE_API_URL=$PulseApiUrl",
        "NODE_ID=$NodeId",
        "COLLECT_INTERVAL=$CollectInterval",
        "SNMP_TARGETS=$SnmpTargets"
    )
    Set-ItemProperty -Path $regPath -Name "Environment" -Value $envVars

    # Configure recovery actions (restart on failure)
    sc.exe failure $ServiceName reset= 60 actions= restart/5000/restart/10000/restart/30000 | Out-Null

    # Start the service
    Start-Service -Name $ServiceName
    Start-Sleep 3

    $svc = Get-Service -Name $ServiceName
    if ($svc.Status -eq "Running") {
        Log-OK "Service '$ServiceName' is running"
    } else {
        Log-Warn "Service status: $($svc.Status) — check Event Viewer for errors"
    }
}

# ── Connectivity check ────────────────────────────────────────────────────────
function Test-Connectivity {
    Log-Info "Testing connectivity to $PulseApiUrl ..."
    try {
        $r = Invoke-WebRequest -Uri "$PulseApiUrl/health" -TimeoutSec 5 -UseBasicParsing
        if ($r.StatusCode -eq 200) { Log-OK "API reachable" }
    } catch {
        Log-Warn "Cannot reach $PulseApiUrl — agent will retry automatically"
    }
}

# ── Windows Event Log source ──────────────────────────────────────────────────
function Register-EventLog {
    if (-not [System.Diagnostics.EventLog]::SourceExists("PulseAgent")) {
        [System.Diagnostics.EventLog]::CreateEventSource("PulseAgent", "Application")
        Log-OK "Event Log source registered"
    }
}

# ── Firewall rule (allow SNMP outbound) ──────────────────────────────────────
function Add-FirewallRules {
    try {
        New-NetFirewallRule -DisplayName "PULSE Agent SNMP" -Direction Outbound `
            -Protocol UDP -RemotePort 161 -Action Allow -ErrorAction SilentlyContinue | Out-Null
        Log-OK "Firewall rule added for SNMP outbound (UDP 161)"
    } catch {}
}

# ── Main ─────────────────────────────────────────────────────────────────────
Write-Banner
if ($Uninstall) { Uninstall-Agent }

Assert-Admin
Assert-Python
Test-Connectivity
Install-AgentFiles
$pyPath = Install-Wrapper
Register-EventLog
Add-FirewallRules
Install-Service -PythonPath $pyPath

Write-Host ""
Write-Host "════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  PULSE agent installed successfully!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Node ID:     $NodeId"
Write-Host "  API:         $PulseApiUrl"
Write-Host "  Install dir: $InstallDir"
Write-Host ""
Write-Host "  Useful commands:"
Write-Host "    Status:    Get-Service $ServiceName"
Write-Host "    Logs:      Get-EventLog -LogName Application -Source PulseAgent -Newest 50"
Write-Host "    Stop:      Stop-Service $ServiceName"
Write-Host "    Remove:    .\install.ps1 -Uninstall"
Write-Host ""
