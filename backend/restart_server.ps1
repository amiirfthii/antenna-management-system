# Restart backend so new PMO mapping routes load.
$ErrorActionPreference = "Continue"
$port = 8000
$root = $PSScriptRoot

Write-Host "Stopping anything on port $port ..."
try {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            if ($_ -and $_ -ne 0) {
                Write-Host "  taskkill PID $_"
                taskkill /F /T /PID $_ | Out-Null
            }
        }
} catch {}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'uvicorn|app\.main' } |
    ForEach-Object {
        Write-Host "  taskkill uvicorn PID $($_.ProcessId)"
        taskkill /F /T /PID $_.ProcessId | Out-Null
    }

Start-Sleep -Seconds 2
Set-Location $root
Write-Host "Starting uvicorn on http://127.0.0.1:$port ..."
Start-Process -FilePath "$root\venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$port","--reload" -WorkingDirectory $root
Start-Sleep -Seconds 4

try {
    $req = [System.Net.WebRequest]::Create("http://127.0.0.1:$port/openapi.json")
    $req.Timeout = 8000
    $resp = $req.GetResponse()
    $json = New-Object System.IO.StreamReader($resp.GetResponseStream()).ReadToEnd()
    $resp.Close()
    if ($json -match 'pmo-mappings|pmo_mappings') {
        Write-Host "OK: PMO mapping routes are registered."
    } else {
        Write-Host "WARN: PMO mapping routes not found in openapi.json"
    }
} catch {
    Write-Host "WARN: Could not verify server: $_"
}

Write-Host "Done. Open http://127.0.0.1:$port and hard-refresh (Ctrl+F5)."
