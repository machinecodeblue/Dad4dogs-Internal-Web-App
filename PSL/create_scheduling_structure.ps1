# Define the base relative path
$basePath = "operations/forms/scheduling"

# Define the files to create
$files = @(
    "__init__.py",
    "visits.py",
    "timelines.py"

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