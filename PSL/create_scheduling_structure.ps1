# Base directory
$base = "operations/tests"

# Top-level files
$rootFiles = @(
    "__init__.py",
    "conftest.py"
)

# Subdirectories and their files
$structure = @{
    "customers" = @(
        "__init__.py",
        "test_forms.py",
        "test_views.py",
        "test_compliance.py",
        "test_contacts.py",
        "test_intake.py"
    )
    "scheduling" = @(
        "__init__.py",
        "test_visits.py",
        "test_checkin.py",
        "test_capacity.py",
        "test_agenda.py",
        "test_pricing.py",
        "test_calendar.py"
    )
    "feed" = @(
        "__init__.py",
        "test_timeline.py",
        "test_interactions.py",
        "test_pwa.py"
    )
}

# Create base directory
if (-not (Test-Path $base)) {
    New-Item -ItemType Directory -Path $base -Force | Out-Null
}

# Create root-level files
foreach ($file in $rootFiles) {
    $path = Join-Path $base $file
    if (-not (Test-Path $path)) {
        New-Item -ItemType File -Path $path -Force | Out-Null
    }
}

# Create subdirectories and files
foreach ($folder in $structure.Keys) {
    $folderPath = Join-Path $base $folder

    if (-not (Test-Path $folderPath)) {
        New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
    }

    foreach ($file in $structure[$folder]) {
        $filePath = Join-Path $folderPath $file
        if (-not (Test-Path $filePath)) {
            New-Item -ItemType File -Path $filePath -Force | Out-Null
        }
    }
}