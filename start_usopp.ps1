param([switch]$NoBrowser, [switch]$CheckOnly, [switch]$Lan, [int]$Port=0,
      [ValidateSet('Start','Stop','Restart')][string]$Action='Start')
$ErrorActionPreference='Stop'
$AppRoot=$PSScriptRoot
. (Join-Path $AppRoot 'model_process.ps1')
Set-Location -LiteralPath $AppRoot
$LogDir=Join-Path $AppRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Resolve paths relative to this script, including after moving the application.
$EnvFile=Join-Path $AppRoot '.env'
if(Test-Path -LiteralPath $EnvFile){
    foreach($Line in Get-Content -LiteralPath $EnvFile){
        if($Line -match '^\s*(USOPP_[A-Z_]+)\s*=\s*(.*?)\s*$'){
            if(-not [Environment]::GetEnvironmentVariable($Matches[1])){
                [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2].Trim('"').Trim("'"),'Process')
            }
        }
    }
}
if(-not $Port){$Port=if($env:USOPP_API_PORT){[int]$env:USOPP_API_PORT}else{8200}}
if($Port -lt 8200 -or $Port -gt 8500){throw 'Choose an application port between 8200 and 8500.'}
$env:USOPP_API_PORT=[string]$Port
if($Action -eq 'Stop'){
    if($CheckOnly){Write-Host "uSOPp.ai stop selected for port $Port; no process changed.";exit 0}
    & (Join-Path $AppRoot 'stop_usopp.ps1') -Port $Port
    exit 0
}
if($Lan){$env:USOPP_API_HOST='0.0.0.0'}
$env:PYTHONUTF8='1'
$env:USOPP_NO_BROWSER='1'
$Python=Join-Path $AppRoot '.venv\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $Python)){
    throw 'Local Python environment is missing. Run setup_usopp.ps1 once, then start again.'
}
if(-not (Test-Path -LiteralPath (Join-Path $AppRoot 'dist\index.html'))){
    throw 'Built interface is missing. Run setup_usopp.ps1 to build it.'
}
if(-not (Test-Path -LiteralPath (Join-Path $AppRoot 'dist\nami\index.html'))){
    throw 'PLC Data interface is missing. Run setup_usopp.ps1 to build both interfaces.'
}
& $Python -c 'import backend.app'
if($LASTEXITCODE -ne 0){throw 'Backend preflight failed. See the error above and logs. Run setup_usopp.ps1 to repair dependencies.'}
$ServerScript=Join-Path $AppRoot 'server.py'
$VirtualPlcScript=Join-Path $AppRoot 'virtual_plc_server.py'
if(Test-Path -LiteralPath $VirtualPlcScript){
    if(-not(Test-Path -LiteralPath (Join-Path $AppRoot 'virtual_plc\dist\index.html'))){
        throw 'Virtual PLC interface is missing. Build it with: node node_modules/vite/bin/vite.js build --config virtual_plc/vite.config.ts'
    }
    & $Python -c 'from virtual_plc.server import create_app; create_app()'
    if($LASTEXITCODE -ne 0){throw 'Virtual PLC preflight failed. See the error above and logs.'}
    $ServerScript=$VirtualPlcScript
}
$Version=(Get-Content -Raw -LiteralPath (Join-Path $AppRoot 'package.json') | ConvertFrom-Json).version
$Url="http://127.0.0.1:$Port"
if($CheckOnly){Write-Host "uSOPp.ai $Version ready: $AppRoot | $Url";exit 0}
if($Action -eq 'Restart'){
    & (Join-Path $AppRoot 'stop_usopp.ps1') -Port $Port
}
function Get-AppHealth {
    try { return Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2 } catch { return $null }
}
$Health=Get-AppHealth
if($Health){
    if($Health.applicationRoot -ne $AppRoot -or $Health.version -ne $Version){
        throw "Port $Port belongs to another app or older revision. Close its server or choose -Port 8201."
    }
    if(-not $Health.capabilities.accounts){
        throw "The server on port $Port predates account support. Finish active jobs, then run Start_uSOPp.bat restart -Port $Port."
    }
    if($ServerScript -eq $VirtualPlcScript){
        try{$VirtualPlcNavigation=Invoke-WebRequest -UseBasicParsing -Uri "$Url/virtual-plc/navigation.js" -TimeoutSec 3}
        catch{throw "This server does not include Virtual PLC. Finish active jobs, then run Start_uSOPp.bat restart -Port $Port."}
        if(-not $VirtualPlcNavigation.Content.Contains('__usoppVirtualNavigation')){
            throw "This server does not include Virtual PLC. Finish active jobs, then run Start_uSOPp.bat restart -Port $Port."
        }
    }
    Write-Host "Using running uSOPp.ai $Version at $Url"
    if($Lan){
        $LanListener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -eq '0.0.0.0' }
        if(-not $LanListener){throw 'The running server is not in LAN mode. Run Start_uSOPp.bat restart -Lan.'}
    }
}else{
    Stop-OwnedChopperModel -ApplicationRoot $AppRoot -OrphanOnly
    $Listener=New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback,$Port)
    try{$Listener.Start()}catch{throw "Port $Port is already occupied. Use -Port 8201 or close the existing server."}finally{$Listener.Stop()}
    $Stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
    $OutLog=Join-Path $LogDir "server_${Stamp}.out.log"
    $ErrLog=Join-Path $LogDir "server_${Stamp}.err.log"
    $Process=Start-Process -FilePath $Python -ArgumentList @('-u',('"'+$ServerScript+'"')) -WorkingDirectory $AppRoot -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru
    $Ready=$false
    for($Attempt=0;$Attempt -lt 30;$Attempt++){
        Start-Sleep -Milliseconds 500
        $Process.Refresh()
        if($Process.HasExited){throw "Backend exited. Read $ErrLog"}
        $Health=Get-AppHealth
        if($Health -and $Health.applicationRoot -eq $AppRoot -and $Health.version -eq $Version -and $Health.capabilities.accounts){
            if($ServerScript -eq $VirtualPlcScript){
                try{$VirtualPlcNavigation=Invoke-WebRequest -UseBasicParsing -Uri "$Url/virtual-plc/navigation.js" -TimeoutSec 2}
                catch{continue}
                if(-not $VirtualPlcNavigation.Content.Contains('__usoppVirtualNavigation')){continue}
            }
            $Ready=$true;break
        }
    }
    if(-not $Ready){throw "Backend did not become ready. Read $ErrLog"}
    @{pid=$Process.Id;port=$Port;root=$AppRoot;version=$Version} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $LogDir 'server_state.json') -Encoding UTF8
    Write-Host "uSOPp.ai $Version started: $Url | PID $($Process.Id)"
}
if(-not $NoBrowser){Start-Process $Url}
