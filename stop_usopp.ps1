param([int]$Port=0)
$ErrorActionPreference='Stop'
$AppRoot=$PSScriptRoot
. (Join-Path $AppRoot 'model_process.ps1')
if(-not $Port){
    if($env:USOPP_API_PORT){$Port=[int]$env:USOPP_API_PORT}
    else{
        $StateFile=Join-Path $AppRoot 'logs\server_state.json'
        if(Test-Path -LiteralPath $StateFile){
            $State=Get-Content -Raw -LiteralPath $StateFile | ConvertFrom-Json
            if($State.root -eq $AppRoot){$Port=[int]$State.port}
        }
        if(-not $Port){$Port=8200}
    }
}
if($Port -lt 1024 -or $Port -gt 65535){throw 'Choose a port between 1024 and 65535.'}
$Listeners=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if(-not $Listeners){Stop-OwnedChopperModel -ApplicationRoot $AppRoot -OrphanOnly;Write-Host "uSOPp.ai is already stopped on port $Port.";exit 0}
$ServerScripts=@((Join-Path $AppRoot 'server.py'),(Join-Path $AppRoot 'virtual_plc_server.py'))
foreach($ServerProcessId in ($Listeners.OwningProcess | Sort-Object -Unique)){
    $ServerProcess=Get-CimInstance Win32_Process -Filter "ProcessId = $ServerProcessId"
    # Verify the exact script in this checkout, never stop every Python process.
    $Command=[string]$ServerProcess.CommandLine
    $ScriptMatches=$false
    foreach($ServerScript in $ServerScripts){
        $QuotedScript='"'+$ServerScript+'"'
        if($Command.Contains($QuotedScript) -or $Command.EndsWith(' '+$ServerScript)){$ScriptMatches=$true;break}
    }
    if(-not $ScriptMatches){throw "Port $Port belongs to a process outside this start script. Refusing to stop PID $ServerProcessId."}
    Stop-OwnedChopperModel -ApplicationRoot $AppRoot -ParentProcessId $ServerProcessId
    Stop-Process -Id $ServerProcessId -ErrorAction Stop
    Write-Host "Stopped uSOPp.ai on port $Port (PID $ServerProcessId)."
}
