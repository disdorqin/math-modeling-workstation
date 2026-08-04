<#
.SYNOPSIS
    One-click launcher for the math modeling workstation web shell.

.DESCRIPTION
    Starts uvicorn against webapp.main:app from the project root.
    No API key is read, written, or printed by this script. Secrets stay in
    .env.local, which the existing CLI helper loads at runtime.

.EXAMPLE
    .\webapp\run.ps1
    .\webapp\run.ps1 -Port 8080 -OutputRoot "D:\cases" -Reload
#>
[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [string]$OutputRoot = "",
    [string]$Python = "",
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

# Project root = parent of this script's directory.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
Write-Host "[web-shell] project root : $ProjectRoot" -ForegroundColor Cyan

# --- resolve interpreter -------------------------------------------------
function Resolve-Python {
    param([string]$Preferred)
    if ($Preferred) {
        if (Test-Path $Preferred) { return $Preferred }
        throw "指定的 Python 不存在: $Preferred"
    }
    $candidates = @(
        "D:\computer learning\Python learning\python\python.exe",
        "python"
    )
    foreach ($candidate in $candidates) {
        try {
            $probe = & $candidate -c "import mathworkstation, fastapi, uvicorn; print('ok')" 2>$null
            if ($probe -eq "ok") { return $candidate }
        } catch { }
    }
    throw "找不到同时具备 mathworkstation + fastapi + uvicorn 的 Python。请先运行: python -m pip install -e . ; python -m pip install -r webapp\requirements.txt"
}

$PythonExe = Resolve-Python -Preferred $Python
Write-Host "[web-shell] interpreter  : $PythonExe" -ForegroundColor Cyan

if ($OutputRoot) {
    $env:MATHWS_OUTPUT_ROOT = $OutputRoot
    Write-Host "[web-shell] output root  : $OutputRoot" -ForegroundColor Cyan
} else {
    Write-Host "[web-shell] output root  : output (default)" -ForegroundColor Cyan
}

$uvicornArgs = @("-m", "uvicorn", "webapp.main:app", "--host", $BindHost, "--port", $Port)
if ($Reload) { $uvicornArgs += "--reload" }

Write-Host ""
Write-Host "  ➜  http://$BindHost`:$Port" -ForegroundColor Green
Write-Host "     Ctrl+C 停止" -ForegroundColor DarkGray
Write-Host ""

& $PythonExe @uvicornArgs
