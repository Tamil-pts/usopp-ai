param([int]$Port=8200, [switch]$Lan, [switch]$NoBrowser, [switch]$Build, [switch]$ReplaceCurrent)
$ErrorActionPreference='Stop'
$VirtualPlcRoot=$PSScriptRoot
Set-Location -LiteralPath $VirtualPlcRoot
$VirtualPlcEnv=Join-Path $VirtualPlcRoot '.env'
if(Test-Path -LiteralPath $VirtualPlcEnv){
    foreach($VirtualPlcLine in Get-Content -LiteralPath $VirtualPlcEnv){
        if($VirtualPlcLine -match '^\s*(USOPP_[A-Z_]+)\s*=\s*(.*?)\s*$'){
            if(-not [Environment]::GetEnvironmentVariable($Matches[1])){
                [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2].Trim('"').Trim("'"),'Process')
            }
        }
    }
}
if($Port -lt 8200 -or $Port -gt 8500){throw 'Choose a port from 8200 through 8500.'}
$VirtualPlcPython=Join-Path $VirtualPlcRoot '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $VirtualPlcPython)){throw 'Run the existing setup_usopp.ps1 to install application dependencies first.'}
if($Build -or -not(Test-Path -LiteralPath (Join-Path $VirtualPlcRoot 'virtual_plc\dist\index.html'))){
    $VirtualPlcNode=Get-Command node -ErrorAction SilentlyContinue
    if(-not $VirtualPlcNode){throw 'Node.js 20 or later is needed to build the new interface. Existing application files are not rebuilt.'}
    & $VirtualPlcNode.Source (Join-Path $VirtualPlcRoot 'node_modules\vite\bin\vite.js') build --config (Join-Path $VirtualPlcRoot 'virtual_plc\vite.config.ts')
    if($LASTEXITCODE -ne 0){throw 'Virtual PLC interface build failed.'}
}
$VirtualPlcListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $Port)
if($VirtualPlcListeners){
    if(-not $ReplaceCurrent){throw "Port $Port is already active. Finish active jobs, then use -ReplaceCurrent to restart this checkout with Virtual PLC. The existing files and results will be retained."}
    foreach($VirtualPlcProcessId in ($VirtualPlcListeners.OwningProcess | Sort-Object -Unique)){
        $VirtualPlcProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$VirtualPlcProcessId"
        $VirtualPlcCommand=[string]$VirtualPlcProcess.CommandLine
        if($VirtualPlcCommand.Contains(('"'+(Join-Path $VirtualPlcRoot 'virtual_plc_server.py')+'"'))){
            & (Join-Path $VirtualPlcRoot 'Stop_Virtual_PLC.ps1') -Port $Port
        }elseif($VirtualPlcCommand.Contains(('"'+(Join-Path $VirtualPlcRoot 'server.py')+'"'))){
            & (Join-Path $VirtualPlcRoot 'stop_usopp.ps1') -Port $Port
        }else{throw "Port $Port belongs to another process. No process was stopped."}
    }
}
$env:USOPP_API_PORT=[string]$Port
$env:USOPP_NO_BROWSER='1'
$env:PYTHONUTF8='1'
$VirtualPlcHost=if($Lan){'0.0.0.0'}else{'127.0.0.1'}
$VirtualPlcLog=Join-Path $VirtualPlcRoot 'logs'
New-Item -ItemType Directory -Force -Path $VirtualPlcLog | Out-Null
$VirtualPlcStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$VirtualPlcScript=Join-Path $VirtualPlcRoot 'virtual_plc_server.py'
$VirtualPlcStarted=Start-Process -FilePath $VirtualPlcPython -ArgumentList @('-u',('"'+$VirtualPlcScript+'"'),'--port',[string]$Port,'--host',$VirtualPlcHost) -WorkingDirectory $VirtualPlcRoot -RedirectStandardOutput (Join-Path $VirtualPlcLog "virtual_plc_$VirtualPlcStamp.out.log") -RedirectStandardError (Join-Path $VirtualPlcLog "virtual_plc_$VirtualPlcStamp.err.log") -WindowStyle Hidden -PassThru
$VirtualPlcReady=$false
for($VirtualPlcAttempt=0;$VirtualPlcAttempt -lt 45;$VirtualPlcAttempt++){
    Start-Sleep -Milliseconds 500
    $VirtualPlcStarted.Refresh()
    if($VirtualPlcStarted.HasExited){throw "Virtual PLC exited. Read logs\virtual_plc_$VirtualPlcStamp.err.log."}
    try{
        $VirtualPlcResponse=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/virtual-plc/" -TimeoutSec 2
        if($VirtualPlcResponse.StatusCode -eq 200 -and $VirtualPlcResponse.Content.Contains('/virtual-plc/assets/')){
            $VirtualPlcStarted.Refresh()
            if(-not $VirtualPlcStarted.HasExited){$VirtualPlcReady=$true;break}
        }
    }catch{}
}
if(-not $VirtualPlcReady){throw "Virtual PLC is still starting. Read logs\virtual_plc_$VirtualPlcStamp.err.log."}
Write-Host "Virtual PLC 0.4.1 ready: http://127.0.0.1:$Port/virtual-plc/"
if(-not $NoBrowser){Start-Process "http://127.0.0.1:$Port/virtual-plc/"}

