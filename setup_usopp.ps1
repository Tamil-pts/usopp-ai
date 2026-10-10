param([string]$PythonPath='', [string]$NodePath='', [switch]$Repair)
$ErrorActionPreference='Stop'
$AppRoot=$PSScriptRoot
Set-Location -LiteralPath $AppRoot
function Resolve-Runtime($Given,$Command,$Bundled){
    if($Given -and (Test-Path -LiteralPath $Given)){return (Resolve-Path -LiteralPath $Given).Path}
    $Candidate=Join-Path $AppRoot $Bundled
    if(Test-Path -LiteralPath $Candidate){return $Candidate}
    $Found=Get-Command $Command -ErrorAction SilentlyContinue
    if($Found){return $Found.Source}
    return ''
}
$PythonPath=Resolve-Runtime $PythonPath 'python' '.runtime\python\python.exe'
$NodePath=Resolve-Runtime $NodePath 'node' '.runtime\node\node.exe'
# Migrate an existing portable Node selection without executing a batch configuration.
if(-not $NodePath -and (Test-Path -LiteralPath (Join-Path $AppRoot 'usopp_paths.bat'))){
    foreach($Line in Get-Content -LiteralPath (Join-Path $AppRoot 'usopp_paths.bat')){
        if($Line -match '^set "USOPP_NODE=(.+)"$' -and (Test-Path -LiteralPath $Matches[1])){$NodePath=$Matches[1]}
    }
}
if(-not $NodePath){throw 'Specify -NodePath with the full path to a portable node.exe.'}
$Npm=Join-Path (Split-Path -Parent $NodePath) 'npm.cmd'
if(-not (Test-Path -LiteralPath $Npm)){throw 'npm.cmd must be beside node.exe.'}
$Venv=Join-Path $AppRoot '.venv'
$VenvPython=Join-Path $Venv 'Scripts\python.exe'
if(-not (Test-Path -LiteralPath $VenvPython)){
    if(-not $PythonPath){throw 'Specify -PythonPath with a user-accessible python.exe.'}
    & $PythonPath -m venv $Venv
    if($LASTEXITCODE -ne 0){throw 'Could not create local Python environment.'}
}
$env:PYTHONUTF8='1'
$PreviousErrorPreference=$ErrorActionPreference
$ErrorActionPreference='Continue'
& $VenvPython -c 'import fastapi,uvicorn,multipart,openpyxl,requests,xlrd,reportlab,docx' 2>$null
$DependencyExitCode=$LASTEXITCODE
$ErrorActionPreference=$PreviousErrorPreference
if($Repair -or $DependencyExitCode -ne 0){
    & $VenvPython -m pip install -r (Join-Path $AppRoot 'backend_requirements.txt') --disable-pip-version-check
    if($LASTEXITCODE -ne 0){throw 'Backend dependency installation failed.'}
}
$env:PATH=(Split-Path -Parent $NodePath)+';'+$env:PATH
if($Repair -or -not (Test-Path -LiteralPath (Join-Path $AppRoot 'node_modules\vite\bin\vite.js'))){
    & $Npm ci --no-audit --no-fund
    if($LASTEXITCODE -ne 0){throw 'Frontend dependency installation failed.'}
}
& $Npm run build
if($LASTEXITCODE -ne 0){throw 'Frontend build failed.'}
& (Join-Path $AppRoot 'start_usopp.ps1') -CheckOnly
if($LASTEXITCODE -ne 0){throw 'Application preflight failed.'}
Write-Host 'Setup complete. Run Start_uSOPp.bat.'
