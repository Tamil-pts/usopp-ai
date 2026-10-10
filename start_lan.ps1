$ErrorActionPreference = 'Stop'
# Close the existing application before starting in LAN mode.
$env:USOPP_API_HOST = '0.0.0.0'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath "$PSScriptRoot\uSOPp_AI.exe") {
    & "$PSScriptRoot\uSOPp_AI.exe"
} elseif (Test-Path -LiteralPath "$PSScriptRoot\.venv\Scripts\python.exe") {
    & "$PSScriptRoot\.venv\Scripts\python.exe" -u "$PSScriptRoot\server.py"
} else {
    py -u "$PSScriptRoot\server.py"
}
