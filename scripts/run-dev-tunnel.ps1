# Start HTTPS Django dev server and expose it through ngrok.
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CertDir = Join-Path $ProjectRoot 'certs'
$CertFile = Join-Path $CertDir 'localhost+2.pem'
$KeyFile = Join-Path $CertDir 'localhost+2-key.pem'
$Port = 9000

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    throw 'ngrok is not installed.'
}

if (-not (Test-Path $CertFile) -or -not (Test-Path $KeyFile)) {
    Write-Host 'Certificates missing — running setup first...'
    & (Join-Path $PSScriptRoot 'setup-certs.ps1')
}

Set-Location $ProjectRoot

Write-Host "Starting HTTPS Django on https://127.0.0.1:$Port ..."
$server = Start-Process python -ArgumentList 'manage.py', 'runserver_https', "$Port" -PassThru -WorkingDirectory $ProjectRoot

Start-Sleep -Seconds 3

Write-Host 'Starting ngrok tunnel (public HTTPS URL will appear below)...'
Write-Host 'Local inspector: http://127.0.0.1:4040'
Write-Host 'Press Ctrl+C to stop ngrok. Then stop the Django server in its window.'
Write-Host ''

try {
    ngrok http "https://127.0.0.1:$Port"
}
finally {
    if (-not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}