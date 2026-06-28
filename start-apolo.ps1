<#
.SYNOPSIS
    Arranca la API de Genix Apolo CAD (FastAPI/uvicorn) en el puerto indicado.

.DESCRIPTION
    Sirve la API REST/WebSocket y la UI compilada en http://127.0.0.1:<puerto>.
    El servidor MCP 'apolo-cad' se conecta a esta API, asi que debe estar arriba
    antes de usar las herramientas MCP desde Claude.

    El script se autolocaliza ($PSScriptRoot), por lo que funciona aunque lo
    invoques desde otra carpeta o con doble clic.

.PARAMETER Port
    Puerto de escucha. Por defecto 8000 (el que espera APOLO_URL del MCP).

.PARAMETER Reload
    Activa la recarga en caliente de uvicorn (util al desarrollar el backend).

.PARAMETER OpenBrowser
    Abre la UI en el navegador una vez levantado.

.EXAMPLE
    .\start-apolo.ps1
    Arranca en el puerto 8000.

.EXAMPLE
    .\start-apolo.ps1 -Port 8001 -OpenBrowser
    Arranca en 8001 y abre el navegador (recuerda ajustar APOLO_URL del MCP).
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$core   = Join-Path $root "core"

Write-Host "== Genix Apolo CAD ==" -ForegroundColor Cyan

if (-not (Test-Path $python)) {
    Write-Host "No se encontro el entorno virtual en:" -ForegroundColor Red
    Write-Host "  $python"
    Write-Host "Crealo con:  python -m venv .venv ; .\.venv\Scripts\pip install -e .\core[dev]"
    exit 1
}

if (-not (Test-Path (Join-Path $core "apolo"))) {
    Write-Host "No se encontro el paquete 'apolo' en $core" -ForegroundColor Red
    exit 1
}

$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Host "El puerto $Port ya esta en uso (PID $($inUse[0].OwningProcess))." -ForegroundColor Yellow
    Write-Host "Quiza la API ya esta corriendo. Abriendo http://127.0.0.1:$Port" -ForegroundColor Yellow
    if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port" }
    exit 0
}

$uvArgs = @("-m", "uvicorn", "apolo.api.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $uvArgs += "--reload" }

Write-Host "Python : $python"
Write-Host "Paquete: $core"
Write-Host "URL    : http://127.0.0.1:$Port  (UI + API)"
Write-Host "MCP    : asegurate de que APOLO_URL=http://127.0.0.1:$Port"
Write-Host "Detener: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

if ($OpenBrowser) {
    Start-Job -ScriptBlock {
        param($p)
        for ($i = 0; $i -lt 30; $i++) {
            try {
                if ((Invoke-WebRequest "http://127.0.0.1:$p/api/scene" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) {
                    Start-Process "http://127.0.0.1:$p"; break
                }
            } catch { Start-Sleep -Milliseconds 500 }
        }
    } -ArgumentList $Port | Out-Null
}

Push-Location $core
try {
    & $python @uvArgs
}
finally {
    Pop-Location
}
