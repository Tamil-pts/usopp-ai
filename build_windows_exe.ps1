param(
    [switch]$SingleFile,
    [switch]$RebuildFrontend
)

$ErrorActionPreference = 'Stop'
$AppRoot = $PSScriptRoot
Set-Location -LiteralPath $AppRoot

$Python = Join-Path $AppRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'The project .venv is missing. Run setup_usopp.ps1 once on this build PC.'
}

if ($RebuildFrontend) {
    $Npm = ''
    $PathsFile = Join-Path $AppRoot 'usopp_paths.bat'
    if (Test-Path -LiteralPath $PathsFile) {
        foreach ($Line in Get-Content -LiteralPath $PathsFile) {
            if ($Line -match '^set "USOPP_NPM=(.+)"$' -and (Test-Path -LiteralPath $Matches[1])) {
                $Npm = $Matches[1]
                break
            }
        }
    }
    if (-not $Npm) {
        $NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if ($NpmCommand) { $Npm = $NpmCommand.Source }
    }
    if (-not $Npm) {
        throw 'npm.cmd was not found on this build PC. Update usopp_paths.bat or omit -RebuildFrontend to package the existing dist folder.'
    }
    $NodeDirectory = Split-Path -Parent $Npm
    $NodeExecutable = Join-Path $NodeDirectory 'node.exe'
    if (-not (Test-Path -LiteralPath $NodeExecutable)) {
        throw "node.exe was not found beside npm.cmd: $NodeDirectory"
    }
    $env:PATH = $NodeDirectory + ';' + $env:PATH
    & $Npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
}

if (-not (Test-Path -LiteralPath (Join-Path $AppRoot 'dist\index.html'))) {
    throw 'dist\index.html is missing. Run this command again with -RebuildFrontend.'
}
if (-not (Test-Path -LiteralPath (Join-Path $AppRoot 'dist\nami\index.html'))) {
    throw 'dist\nami\index.html is missing. Run again with -RebuildFrontend to include PLC Data.'
}
if (-not (Test-Path -LiteralPath (Join-Path $AppRoot 'virtual_plc\dist\index.html'))) {
    throw 'Virtual PLC interface is missing. Run again with -RebuildFrontend.'
}

& $Python -m pip install 'pyinstaller==6.22.3' --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }

$ReleaseRoot = Join-Path $AppRoot ('release\windows-source-free\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$WorkRoot = Join-Path $AppRoot '.build\pyinstaller'
$SpecRoot = Join-Path $AppRoot '.build\spec'
New-Item -ItemType Directory -Force -Path $ReleaseRoot, $WorkRoot, $SpecRoot | Out-Null
$EngineStage = & $Python (Join-Path $AppRoot 'prepare_release.py')
if ($LASTEXITCODE -ne 0) { throw 'Source-free engine staging failed.' }

$Mode = if ($SingleFile) { '--onefile' } else { '--onedir' }
$Arguments = @(
    '--noconfirm',
    '--clean',
    $Mode,
    '--console',
    '--noupx',
    '--name', 'uSOPp_AI',
    '--paths', $AppRoot,
    '--distpath', $ReleaseRoot,
    '--workpath', $WorkRoot,
    '--specpath', $SpecRoot,
    '--add-data', ((Join-Path $AppRoot 'dist') + ';dist'),
    '--add-data', ((Join-Path $EngineStage 'python_engine') + ';python_engine'),
    '--paths', (Join-Path $AppRoot 'python_engine'),
    '--collect-submodules', 'python_engine',
    '--add-data', ((Join-Path $EngineStage 'rules') + ';rules'),
    '--add-data', ((Join-Path $EngineStage 'knowledge') + ';knowledge'),
    '--add-data', ((Join-Path $AppRoot 'package.json') + ';.'),
    '--add-data', ((Join-Path $AppRoot 'src\usopp_logo.png') + ';src'),
    '--add-data', ((Join-Path $AppRoot 'src\petrus_logo.png') + ';src'),
    '--collect-submodules', 'uvicorn',
    '--collect-submodules', 'backend',
    '--collect-submodules', 'virtual_plc.core',
    '--add-data', ((Join-Path $AppRoot 'virtual_plc\dist') + ';virtual_plc/dist'),
    '--add-data', ((Join-Path $AppRoot 'virtual_plc\examples') + ';virtual_plc/examples'),
    '--add-data', ((Join-Path $AppRoot 'virtual_plc\navigation.js') + ';virtual_plc'),
    '--collect-submodules', 'fastapi',
    '--collect-submodules', 'multipart',
    '--collect-submodules', 'openpyxl', '--collect-data', 'openpyxl',
    '--collect-submodules', 'xlrd', '--collect-data', 'xlrd',
    '--collect-submodules', 'reportlab', '--collect-data', 'reportlab',
    '--collect-submodules', 'docx', '--collect-data', 'docx',
    '--collect-submodules', 'pypdf', '--collect-data', 'pypdf',
    '--collect-submodules', 'svglib', '--collect-data', 'svglib',
    '--collect-submodules', 'mcp.server',
    '--collect-submodules', 'mcp.shared',
    '--collect-submodules', 'mcp.client',
    '--exclude-module', 'mcp.cli',
    '--collect-data', 'mcp',
    '--collect-submodules', 'lxml', '--collect-data', 'lxml',
    '--collect-submodules', 'PIL', '--collect-data', 'PIL',
    (Join-Path $AppRoot 'server.py')
)

$LocalRuntime = Join-Path $AppRoot 'local_ai\runtime'
if (Test-Path -LiteralPath (Join-Path $LocalRuntime 'llama-server.exe')) {
    $Arguments = @('--add-data', ($LocalRuntime + ';local_ai/runtime')) + $Arguments
}
$Arguments = @('--add-data', ((Join-Path $AppRoot 'local_ai\MODEL_LICENSE.txt') + ';local_ai'), '--add-data', ((Join-Path $AppRoot 'local_ai\MODEL_CARD.md') + ';local_ai')) + $Arguments

if (-not $SingleFile) {
    $Arguments = @('--contents-directory', '.') + $Arguments
}

# Windows PowerShell treats redirected native stderr (including INFO logs)
# as an error record. Judge this native tool by its exit code instead.
$PreviousErrorPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & $Python -m PyInstaller @Arguments
    $BuildExitCode = $LASTEXITCODE
} finally { $ErrorActionPreference = $PreviousErrorPreference }
if ($BuildExitCode -ne 0) { throw 'Windows EXE build failed.' }

$Output = if ($SingleFile) {
    Join-Path $ReleaseRoot 'uSOPp_AI.exe'
} else {
    Join-Path $ReleaseRoot 'uSOPp_AI\uSOPp_AI.exe'
}

Write-Host ''
Write-Host "Build complete: $Output" -ForegroundColor Green
if (Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File | Where-Object { $_.Extension -in @('.py','.pyw','.tsx','.ts','.map') }) {
    throw 'Release audit failed: raw source or source maps found in the distribution.'
}
Write-Host 'Raw source audit passed. Bytecode is reversible; this is not encryption.'
if (-not $SingleFile) {
    Write-Host "Distribute only the complete $ReleaseRoot\uSOPp_AI folder. The target PC does not need Python, Node, Vite, npm, or administrator access."
} else {
    Write-Host 'The single-file EXE is portable but starts more slowly because its bundled runtime is extracted for each engine process.'
}
