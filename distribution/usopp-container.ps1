param(
    [ValidateSet('install','start','stop','status','logs','update')]
    [string]$Action = 'status',
    [ValidatePattern('^[a-z0-9][a-z0-9._/:@-]+$')]
    [string]$Image,
    [string]$ImageArchive,
    [ValidateRange(8200,8500)]
    [int]$Port = 8200
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop, enable its WSL 2 backend and start it first. See README.md.'
}
$DockerOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $DockerOS -ne 'linux') { throw 'Docker must be running in Linux containers mode.' }
$ConfigRoot = Join-Path $env:LOCALAPPDATA 'uSOPp-container'
$ConfigFile = Join-Path $ConfigRoot 'config.json'
$SecretFile = Join-Path $ConfigRoot 'admin-password.txt'
$ComposeFile = Join-Path $ConfigRoot 'compose.yaml'

if ($Action -in @('install','update')) {
    if (-not $Image) { throw 'Supply -Image usopp-ai:<release version>.' }
    if ($ImageArchive) {
        $ArchivePath = (Resolve-Path -LiteralPath $ImageArchive).Path
        & docker image load --input $ArchivePath
        if ($LASTEXITCODE -ne 0) { throw 'Container image import failed.' }
    }
    & docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        & docker pull $Image
        if ($LASTEXITCODE -ne 0) { throw 'Image unavailable. Load the release image archive or sign in to its registry.' }
    }
    New-Item -ItemType Directory -Force -Path $ConfigRoot | Out-Null
    # Restrict the secret's containing directory to this Windows account and SYSTEM.
    $Acl = New-Object System.Security.AccessControl.DirectorySecurity
    $Acl.SetAccessRuleProtection($true, $false)
    $UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    foreach ($Sid in @($UserSid, (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')))) {
        $Rule = New-Object System.Security.AccessControl.FileSystemAccessRule($Sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $Acl.AddAccessRule($Rule)
    }
    Set-Acl -LiteralPath $ConfigRoot -AclObject $Acl
    if (-not (Test-Path -LiteralPath $SecretFile)) {
        $Secure = Read-Host 'Choose the initial Admin password (12 to 128 characters)' -AsSecureString
        $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
        try {
            $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
            if ($Password.Length -lt 12 -or $Password.Length -gt 128 -or $Password.Contains("`n") -or $Password.Contains("`r")) {
                throw 'Use 12 to 128 characters without line breaks.'
            }
            [IO.File]::WriteAllText($SecretFile, $Password, (New-Object Text.UTF8Encoding($false)))
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
            $Password = $null
        }
    }
    if ($Action -eq 'update' -and (Test-Path -LiteralPath $ConfigFile) -and -not $PSBoundParameters.ContainsKey('Port')) {
        $Port = (Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json).port
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compose.yaml') -Destination $ComposeFile -Force
    @{image=$Image;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $ConfigFile -Encoding UTF8
}
if (-not (Test-Path -LiteralPath $ConfigFile)) { throw 'Run install first. See README.md.' }
$Config = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
$env:USOPP_IMAGE = $Config.image
$env:USOPP_PORT = [string]$Config.port
$env:USOPP_ADMIN_PASSWORD_FILE = $SecretFile.Replace('\','/')
$ComposeArgs = @('compose','--project-name','usopp-container','--file',$ComposeFile)
switch ($Action) {
    { $_ -in @('install','start','update') } {
        & docker @ComposeArgs up -d --pull never
        if ($LASTEXITCODE -ne 0) { throw 'Container startup failed; run logs for details.' }
        Write-Host "Open http://127.0.0.1:$($Config.port). Sign in as Admin with your chosen password."
    }
    'stop' { & docker @ComposeArgs stop }
    'status' { & docker @ComposeArgs ps }
    'logs' { & docker @ComposeArgs logs --tail 100 }
}
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose command failed.' }
