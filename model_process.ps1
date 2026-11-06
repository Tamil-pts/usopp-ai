# Only processes started from this exact checkout are eligible for cleanup.
function Stop-OwnedChopperModel {
    param([string]$ApplicationRoot,[int]$ParentProcessId=0,[switch]$OrphanOnly)
    $RuntimePath=Join-Path $ApplicationRoot 'local_ai\runtime\llama-server.exe'
    foreach($Candidate in @(Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" -ErrorAction SilentlyContinue)){
        if(-not $Candidate.ExecutablePath -or -not [string]::Equals($Candidate.ExecutablePath,$RuntimePath,[StringComparison]::OrdinalIgnoreCase)){continue}
        if($Candidate.CommandLine -notmatch '--alias\s+chopper-(?:local|embedding|reranker)(?:\s|$)' -or $Candidate.CommandLine -notmatch '--host\s+127\.0\.0\.1(?:\s|$)'){continue}
        if($ParentProcessId -and $Candidate.ParentProcessId -ne $ParentProcessId){continue}
        if($OrphanOnly){
            $Parent=Get-CimInstance Win32_Process -Filter "ProcessId = $($Candidate.ParentProcessId)" -ErrorAction SilentlyContinue
            if($Parent -and $Parent.CreationDate -le $Candidate.CreationDate){continue}
        }
        Stop-Process -Id $Candidate.ProcessId -ErrorAction Stop
        Write-Host "Stopped owned Chopper model (PID $($Candidate.ProcessId))."
    }
}
