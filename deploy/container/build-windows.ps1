param(
    [string]$SourceRoot = (Join-Path $PSScriptRoot '..\..'),
    [ValidatePattern('^[a-z0-9][a-z0-9._/:@-]+$')]
    [string]$Image,
    [switch]$Plan
)
$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$PackageFile = Join-Path $SourceRoot 'package.json'
$Dockerfile = Join-Path $SourceRoot 'Dockerfile'
if (-not (Test-Path -LiteralPath $PackageFile) -or -not (Test-Path -LiteralPath $Dockerfile)) {
    throw 'Choose the extracted private source bundle or the current source checkout.'
}
$Version = (Get-Content -LiteralPath $PackageFile -Raw | ConvertFrom-Json).version
if ($Version -notmatch '^\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$') { throw 'Invalid application version in package.json.' }
if (-not $Image) { $Image = "usopp-ai:$Version" }
$BuildArgs = @('build','--pull','--platform','linux/amd64','--target','windows-desktop',
    '--file',$Dockerfile,'--build-arg',"APP_VERSION=$Version",'--tag',$Image)
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $Commit = & git -C $SourceRoot rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $Commit -match '^[0-9a-f]{40,64}$') { $BuildArgs += @('--build-arg',"SOURCE_COMMIT=$Commit") }
    } catch { $Commit = $null }
}
$BuildArgs += $SourceRoot
if ($Plan) {
    [pscustomobject]@{hostProfile='windows-desktop';containerOS='linux';version=$Version;image=$Image;arguments=$BuildArgs} | ConvertTo-Json -Depth 4
    return
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop with Linux containers, then rerun this build command.' }
$DockerOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $DockerOS -ne 'linux') { throw 'Start Docker Desktop and select Linux containers before building.' }
& docker @BuildArgs
if ($LASTEXITCODE -ne 0) { throw 'The Windows Desktop container build failed. No installation or data volume was changed.' }
Write-Host "Built $Image for Docker Desktop on Windows. Install with distribution\usopp-container.ps1."
