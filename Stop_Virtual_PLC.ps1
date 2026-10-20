param([int]$Port=8200)
$ErrorActionPreference='Stop'
$VirtualPlcRoot=$PSScriptRoot
. (Join-Path $VirtualPlcRoot 'model_process.ps1')
$VirtualPlcListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $Port)
foreach($VirtualPlcProcessId in ($VirtualPlcListeners.OwningProcess | Sort-Object -Unique)){
    $VirtualPlcProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$VirtualPlcProcessId"
    $VirtualPlcExpected='"'+(Join-Path $VirtualPlcRoot 'virtual_plc_server.py')+'"'
    if(-not([string]$VirtualPlcProcess.CommandLine).Contains($VirtualPlcExpected)){throw "Port $Port is not this checkout's Virtual PLC process. No process was stopped."}
    Stop-OwnedChopperModel -ApplicationRoot $VirtualPlcRoot -ParentProcessId $VirtualPlcProcessId
    Stop-Process -Id $VirtualPlcProcessId -ErrorAction Stop
    Write-Host "Stopped Virtual PLC on port $Port (PID $VirtualPlcProcessId)."
}
