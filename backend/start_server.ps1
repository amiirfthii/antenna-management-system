# Start antenna backend on port 8000.
# If already running, does NOT start a second copy (avoids WinError 10048).
$ErrorActionPreference = "Continue"
$port = 8000
$url = "http://127.0.0.1:$port"

function Test-ServerUp {
    try {
        $req = [System.Net.WebRequest]::Create("$url/openapi.json")
        $req.Timeout = 3000
        $resp = $req.GetResponse()
        $stream = $resp.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $json = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        if ($json -notmatch 'pmo-mappings|pmo_mappings') {
            Write-Host "Server is running but missing PMO mapping routes (old code). Restarting..."
            return $false
        }
        return $true
    } catch {
        return $false
    }
}

if (Test-ServerUp) {
    Write-Host ""
    Write-Host "Server is ALREADY running on $url"
    Write-Host "Open the browser: $url"
    Write-Host ""
    exit 0
}

# Stop stale server on this port before starting fresh copy.
Write-Host "Freeing port $port (stale process)..."
$listenPids = @()
try {
    $listenPids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
} catch {}

foreach ($procId in $listenPids) {
    if ($procId -and $procId -ne 0) {
        Write-Host "  Killing PID $procId"
        taskkill /F /T /PID $procId 2>$null | Out-Null
    }
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'uvicorn|app\.main' } |
    ForEach-Object {
        Write-Host "  Killing uvicorn python $($_.ProcessId)"
        taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
    }

Start-Sleep -Seconds 1
Set-Location $PSScriptRoot
Write-Host "Starting server on $url ..."
& "$PSScriptRoot\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port --reload
