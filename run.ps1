$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    $projectPython = (Get-Command python -ErrorAction Stop).Source
}
Push-Location -LiteralPath $projectRoot
try {
    & $projectPython (Join-Path $projectRoot 'netlab.py') @args
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
