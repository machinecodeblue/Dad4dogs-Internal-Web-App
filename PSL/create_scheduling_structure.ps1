# Define the base relative path
$basePath = "operations/models/scheduling"

# Define the files to create
$files = @(
    "__init__.py",
    "series.py",
    "visits.py",
    "media.py",
    "timeline.py",
    "interactions.py",
    "calendar.py"
)

# Ensure the directory exists
if (-not (Test-Path $basePath)) {
    New-Item -ItemType Directory -Path $basePath -Force | Out-Null
}

# Create each file inside the directory
foreach ($file in $files) {
    $fullPath = Join-Path $basePath $file
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType File -Path $fullPath -Force | Out-Null
    }
}