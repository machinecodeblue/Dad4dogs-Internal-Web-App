# Define the base relative path
$basePath = "operations/capacity"

# Define the files to create
$files = @(
    "__init__.py",
    "limits.py",
    "spans.py",
    "engine.py"
)

# Create each file inside the directory
foreach ($file in $files) {
    $fullPath = Join-Path $basePath $file
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType File -Path $fullPath -Force | Out-Null
    }
}