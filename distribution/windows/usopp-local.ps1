param(
    [ValidateSet('start','stop','status')]
    [string]$Action = 'start',
    [ValidateRange(8200,8500)]
    [int]$Port = 8200
)
$ErrorActionPreference = 'Stop'
$Executable = Join-Path $PSScriptRoot 'uSOPp_AI.exe'
if (-not (Test-Path -LiteralPath $Executable)) { throw 'Keep the launcher in the complete extracted uSOPp_AI folder.' }
$Processes = @(Get-CimInstance Win32_Process -Filter "Name='uSOPp_AI.exe'" |
    Where-Object { $_.ExecutablePath -eq $Executable })
switch ($Action) {
    'start' {
        $env:USOPP_API_PORT = [string]$Port
        $env:USOPP_API_HOST = '127.0.0.1'
        Start-Process -FilePath $Executable -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        Write-Host "uSOPp launch requested on http://127.0.0.1:$Port. The application opens your browser."
    }
    'status' {
        if ($Processes.Count) { $Processes | Select-Object ProcessId,ExecutablePath }
        else { Write-Host 'This application folder is stopped.' }
    }
    'stop' {
        # Stop only this extracted package, including its engine children.
        # The user must finish validations before requesting shutdown.
        foreach ($Process in $Processes) { Stop-Process -Id $Process.ProcessId -ErrorAction SilentlyContinue }
        Write-Host 'Stopped this application folder. Saved data was retained.'
    }
}
