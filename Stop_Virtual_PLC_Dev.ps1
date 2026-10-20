param([int]$FrontendPort=8201)
$ErrorActionPreference='Stop'
$VirtualPlcExpected='"'+(Join-Path $PSScriptRoot 'virtual_plc\development.vite.config.ts')+'"'
$VirtualPlcListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $FrontendPort)
foreach($VirtualPlcProcessId in ($VirtualPlcListeners.OwningProcess | Sort-Object -Unique)){
    $VirtualPlcProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$VirtualPlcProcessId"
    if(-not([string]$VirtualPlcProcess.CommandLine).Contains($VirtualPlcExpected)){
        throw "Port $FrontendPort is not this checkout's Virtual PLC development frontend. No process was stopped."
    }
    Stop-Process -Id $VirtualPlcProcessId -ErrorAction Stop
    Write-Host "Stopped Virtual PLC development frontend on port $FrontendPort (PID $VirtualPlcProcessId)."
}
