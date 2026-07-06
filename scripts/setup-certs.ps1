# Generate locally trusted HTTPS certificates with mkcert.
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CertDir = Join-Path $ProjectRoot 'certs'

if (-not (Get-Command mkcert -ErrorAction SilentlyContinue)) {
    throw 'mkcert is not installed. Install with: choco install mkcert'
}

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

Write-Host 'Installing mkcert local CA (one-time, may prompt for admin)...'
mkcert -install

$CertFile = Join-Path $CertDir 'localhost+2.pem'
$KeyFile = Join-Path $CertDir 'localhost+2-key.pem'

Write-Host "Generating certificates in $CertDir ..."
mkcert -key-file $KeyFile -cert-file $CertFile localhost 127.0.0.1 ::1

Write-Host ''
Write-Host 'Done. Certificates created:'
Write-Host "  $CertFile"
Write-Host "  $KeyFile"
Write-Host ''
Write-Host 'Start HTTPS dev server:'
Write-Host '  python manage.py runserver_https 9000'