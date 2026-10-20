param([int]$Port=8200,[int]$FrontendPort=8201,[switch]$ReplaceCurrent,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if($Port -lt 8200 -or $Port -gt 8500 -or $FrontendPort -lt 8200 -or $FrontendPort -gt 8500 -or $Port -eq $FrontendPort){throw 'Use different backend/frontend ports from 8200 through 8500.'}
$VirtualPlcAvailable=$false
try {
    $VirtualPlcPage=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/virtual-plc/" -TimeoutSec 3
    $VirtualPlcNavigation=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/virtual-plc/navigation.js" -TimeoutSec 3
    $VirtualPlcAvailable=$VirtualPlcPage.Content.Contains('/virtual-plc/assets/') -and $VirtualPlcNavigation.Content.Contains('__usoppVirtualNavigation')
}catch{}
if(-not $VirtualPlcAvailable){& (Join-Path $PSScriptRoot 'Start_Virtual_PLC.ps1') -Port $Port -NoBrowser -ReplaceCurrent:$ReplaceCurrent}
$VirtualPlcNode=Get-Command node -ErrorAction SilentlyContinue
if(-not $VirtualPlcNode){throw 'Node.js 20 or later must be available on PATH for frontend development.'}
$VirtualPlcListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $FrontendPort)
if($VirtualPlcListeners){throw "Frontend port $FrontendPort is already active. Stop the previous development frontend or choose another -FrontendPort. No process was stopped."}
$env:USOPP_API_PORT=[string]$Port
$env:USOPP_FRONTEND_PORT=[string]$FrontendPort
$VirtualPlcLog=Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $VirtualPlcLog | Out-Null
$VirtualPlcStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$VirtualPlcVite=Join-Path $PSScriptRoot 'node_modules\vite\bin\vite.js'
$VirtualPlcConfig=Join-Path $PSScriptRoot 'virtual_plc\development.vite.config.ts'
$VirtualPlcStarted=Start-Process -FilePath $VirtualPlcNode.Source -ArgumentList @(('"'+$VirtualPlcVite+'"'),'--config',('"'+$VirtualPlcConfig+'"')) -WorkingDirectory $PSScriptRoot -RedirectStandardOutput (Join-Path $VirtualPlcLog "virtual_plc_dev_$VirtualPlcStamp.out.log") -RedirectStandardError (Join-Path $VirtualPlcLog "virtual_plc_dev_$VirtualPlcStamp.err.log") -WindowStyle Hidden -PassThru
for($VirtualPlcAttempt=0;$VirtualPlcAttempt -lt 40;$VirtualPlcAttempt++){
    Start-Sleep -Milliseconds 500
    $VirtualPlcStarted.Refresh()
    if($VirtualPlcStarted.HasExited){throw "Development frontend exited. Read logs\virtual_plc_dev_$VirtualPlcStamp.err.log."}
    try {
        $VirtualPlcPage=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSec 2
        if($VirtualPlcPage.Content.Contains('/virtual-plc/navigation.js')){
            Write-Host "Development frontend with Virtual PLC: http://127.0.0.1:$FrontendPort/"
            if(-not $NoBrowser){Start-Process "http://127.0.0.1:$FrontendPort/"}
            exit 0
        }
    }catch{}
}
throw "Development frontend is still starting. Read logs\virtual_plc_dev_$VirtualPlcStamp.err.log."
