param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9-]*$')]
    [string]$Owner,
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$SourceName = 'usopp-ai',
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$DownloadsName = 'usopp-distribution'
)
$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $AppRoot
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI and run gh auth login first. See GIT_DISTRIBUTION.md.' }
& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Sign in with gh auth login first.' }
if (-not $Owner) {
    $Owner = & gh api user --jq .login
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the signed-in GitHub account.' }
}
if ($SourceName -eq $DownloadsName) { throw 'Use different repositories for source and downloads.' }
& git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) { throw 'Initialize and review the app Git repository first.' }
$GitRoot = (& git rev-parse --show-toplevel).Trim()
if ((Resolve-Path -LiteralPath $GitRoot).Path -ne $AppRoot) { throw 'The Git repository must contain only the app root, not its customer-project parent.' }
& git log -1 --format=%s
if ($LASTEXITCODE -ne 0) { throw 'Commit the reviewed source first.' }
if (& git status --porcelain) { throw 'Commit or review pending changes before publishing.' }
$ExistingRemote = ''
if ((& git remote) -contains 'origin') { $ExistingRemote = & git remote get-url origin }
if ($ExistingRemote -and $ExistingRemote -ne "https://github.com/$Owner/$SourceName.git") { throw 'An unrelated origin already exists; review it first.' }
foreach ($Name in @($SourceName,$DownloadsName)) {
    $PriorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $Private = & gh repo view "$Owner/$Name" --json isPrivate --jq .isPrivate 2>$null
        $ViewExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $PriorPreference }
    if ($ViewExitCode -ne 0) {
        & gh repo create "$Owner/$Name" --private --description 'uSOPp.ai engineering validation'
        if ($LASTEXITCODE -ne 0) { throw "Private repository creation failed: $Name" }
    } elseif ($Private -ne 'true') { throw "Repository $Name exists and is public; publishing stopped." }
}
& gh auth setup-git
if ($LASTEXITCODE -ne 0) { throw 'Git authentication setup failed.' }
if (-not $ExistingRemote) { & git remote add origin "https://github.com/$Owner/$SourceName.git" }
& git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Source push failed; no force push was attempted.' }
$DownloadStage = Join-Path $AppRoot ('.build\github-downloads\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
& git clone "https://github.com/$Owner/$DownloadsName.git" $DownloadStage
if ($LASTEXITCODE -ne 0) { throw 'Downloads repository clone failed.' }
Set-Location -LiteralPath $DownloadStage
if ((& git branch --show-current).Trim() -ne 'main') {
    throw 'The downloads repository has a different default branch; review it before publishing.'
}
Copy-Item -LiteralPath (Join-Path $AppRoot 'distribution\README.md') -Destination (Join-Path $DownloadStage 'README.md') -Force
& git add README.md
if (& git status --porcelain) {
    & git commit -m 'Update uSOPp package installation instructions'
    if ($LASTEXITCODE -ne 0) { throw 'Downloads README commit failed.' }
}
& git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Downloads push failed; review its existing main branch before retrying. No force push was attempted.' }
Set-Location -LiteralPath $AppRoot
& gh variable set DISTRIBUTION_REPO --repo "$Owner/$SourceName" --body "$Owner/$DownloadsName"
if ($LASTEXITCODE -ne 0) { throw 'Set DISTRIBUTION_REPO manually in repository Actions variables.' }
Write-Host "Private source: https://github.com/$Owner/$SourceName"
Write-Host "Private downloads: https://github.com/$Owner/$DownloadsName"
Write-Host 'See GIT_DISTRIBUTION.md to add the distribution token and build a draft release. Give end users access only to the downloads repository.'
