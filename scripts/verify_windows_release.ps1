param([string]$Executable = '', [int]$Port = 8398)
$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $PSScriptRoot
if ($Port -lt 8200 -or $Port -gt 8500) { throw 'Choose an isolated application port in 8200..8500.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use." }
if (-not $Executable) {
    $Latest = Get-ChildItem -LiteralPath (Join-Path $AppRoot 'release\windows-source-free') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $Latest) { throw 'Build a Windows release first.' }
    $Executable = Join-Path $Latest.FullName 'uSOPp_AI\uSOPp_AI.exe'
}
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$Out = Join-Path $AppRoot ('.build\windows-runtime-smoke\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$PasswordFile = Join-Path $Out 'initial-password.txt'
$Password = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
[IO.File]::WriteAllText($PasswordFile, $Password)
$Version = (Get-Content -Raw -LiteralPath (Join-Path $AppRoot 'package.json') | ConvertFrom-Json).version
$Variables = @{
    USOPP_DATA_ROOT = (Join-Path $Out 'data')
    USOPP_API_PORT = [string]$Port
    USOPP_API_HOST = '127.0.0.1'
    USOPP_NO_BROWSER = '1'
    USOPP_INITIAL_ADMIN_PASSWORD = $Password
    USOPP_PI_WORKER_MODE = 'external'
}
$Previous = @{}
$RuntimeProcess = $null
try {
    foreach ($Key in $Variables.Keys) {
        $Previous[$Key] = [Environment]::GetEnvironmentVariable($Key, 'Process')
        [Environment]::SetEnvironmentVariable($Key, $Variables[$Key], 'Process')
    }
    $RuntimeProcess = Start-Process -FilePath $Executable -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Out 'stdout.log') -RedirectStandardError (Join-Path $Out 'stderr.log')
    & (Join-Path $AppRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'container_smoke.py') --url "http://127.0.0.1:$Port" --version $Version --password-file $PasswordFile
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath (Join-Path $Out 'stderr.log') -Tail 50
        throw 'Frozen Windows application HTTP checks failed.'
    }
    Write-Host "Windows runtime verified. Logs: $Out"
} finally {
    if ($RuntimeProcess -and -not $RuntimeProcess.HasExited) { Stop-Process -Id $RuntimeProcess.Id -Force -ErrorAction SilentlyContinue }
    foreach ($Key in $Previous.Keys) { [Environment]::SetEnvironmentVariable($Key, $Previous[$Key], 'Process') }
    Remove-Item -LiteralPath $PasswordFile -Force -ErrorAction SilentlyContinue
}
