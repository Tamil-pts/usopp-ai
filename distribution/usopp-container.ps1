param(
    [ValidateSet('install','start','stop','status','logs','update','backup','restore')]
    [string]$Action = 'status',
    [ValidatePattern('^[a-z0-9][a-z0-9._/:@-]+$')]
    [string]$Image,
    [string]$ImageArchive,
    [ValidateRange(8200,8500)]
    [int]$Port = 8200,
    [string]$BindAddress = '127.0.0.1',
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.-]+$')]
    [string]$DataVolume = 'usopp-container_data',
    [string]$BackupDirectory,
    [string]$BackupFile
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
$PreviousConfig = if (Test-Path -LiteralPath $ConfigFile) { Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json } else { $null }
if ($Action -eq 'update' -and -not $PreviousConfig) { throw 'Run install before updating a server.' }
if ($Action -eq 'install' -and $PreviousConfig -and $Image -ne $PreviousConfig.image) { throw 'Use update to change an installed release with a full backup.' }
if (-not $BackupDirectory) { $BackupDirectory = Join-Path $ConfigRoot 'backups' }

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
    if ($PreviousConfig) {
        if (-not $PSBoundParameters.ContainsKey('Port')) { $Port = $PreviousConfig.port }
        if (-not $PSBoundParameters.ContainsKey('BindAddress') -and $PreviousConfig.bindAddress) { $BindAddress = $PreviousConfig.bindAddress }
        $ExistingVolume = if ($PreviousConfig.dataVolume) { $PreviousConfig.dataVolume } else { 'usopp-container_data' }
        if ($PSBoundParameters.ContainsKey('DataVolume') -and $DataVolume -ne $ExistingVolume) { throw 'Use restore to switch to a new volume. Updates retain existing data.' }
        $DataVolume = $ExistingVolume
    }
    $ParsedAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($BindAddress,[ref]$ParsedAddress) -or $ParsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'BindAddress must be an IPv4 address belonging to this server, or 0.0.0.0.' }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compose.yaml') -Destination $ComposeFile -Force
    $Config = [pscustomobject]@{image=$Image;port=$Port;bindAddress=$BindAddress;dataVolume=$DataVolume}
} else {
    if (-not (Test-Path -LiteralPath $ConfigFile)) { throw 'Run install first. See README.md.' }
    $Config = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
}
$env:USOPP_IMAGE = $Config.image
$env:USOPP_PORT = [string]$Config.port
$env:USOPP_BIND_ADDRESS = if ($Config.bindAddress) { $Config.bindAddress } else { '127.0.0.1' }
$env:USOPP_DATA_VOLUME = if ($Config.dataVolume) { $Config.dataVolume } else { 'usopp-container_data' }
$env:USOPP_ADMIN_PASSWORD_FILE = $SecretFile.Replace('\','/')
$ComposeArgs = @('compose','--project-name','usopp-container','--file',$ComposeFile)
function Assert-VolumeStopped {
    $Running = & docker ps --filter "volume=$env:USOPP_DATA_VOLUME" --format '{{.ID}}'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot check running containers.' }
    if ($Running) { throw 'Finish active tests and run stop before backup or restore.' }
}
function Save-ServerBackup {
    Assert-VolumeStopped
    New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
    $BackupRoot = (Resolve-Path -LiteralPath $BackupDirectory).Path
    if ($BackupRoot.Contains(',')) { throw 'Use a backup directory without a comma in its path.' }
    if ($BackupRoot.TrimEnd('\') -eq [IO.Path]::GetPathRoot($BackupRoot).TrimEnd('\')) { throw 'Choose a dedicated backup folder, not a drive root.' }
    Set-Acl -LiteralPath $BackupRoot -AclObject (Get-Acl -LiteralPath $ConfigRoot)
    $BackupName = 'usopp-server-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.tar.gz'
    & docker run --rm --network none --user 0 --entrypoint python --env USOPP_DATA_ROOT=/data --mount "type=volume,source=$env:USOPP_DATA_VOLUME,target=/data,readonly" --mount "type=bind,source=$BackupRoot,target=/backup" $Config.image /opt/usopp/container_maintenance.pyc backup "/backup/$BackupName"
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed. The app was left stopped; existing data was retained.' }
    Write-Host "Backup and checksum: $(Join-Path $BackupRoot $BackupName)"
}
if ($Action -eq 'install') { & docker volume create $env:USOPP_DATA_VOLUME | Out-Null }
else { & docker volume inspect $env:USOPP_DATA_VOLUME *> $null }
if ($LASTEXITCODE -ne 0) { throw 'The persistent data volume is missing. Restore a backup; do not start with an empty replacement.' }
if ($Action -eq 'update') {
    & docker @ComposeArgs stop
    if ($LASTEXITCODE -ne 0) { throw 'Cannot stop the old application for backup.' }
    Save-ServerBackup
}
if ($Action -in @('install','update')) { $Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigFile -Encoding UTF8 }
switch ($Action) {
    { $_ -in @('install','start','update') } {
        & docker @ComposeArgs up -d --pull never
        if ($LASTEXITCODE -ne 0) { throw 'Container startup failed; run logs for details.' }
        $DisplayAddress = if ($env:USOPP_BIND_ADDRESS -eq '0.0.0.0') { '<server-LAN-IP>' } else { $env:USOPP_BIND_ADDRESS }
        Write-Host "Open http://${DisplayAddress}:$($Config.port). Sign in as Admin with your chosen password."
    }
    'stop' { & docker @ComposeArgs stop }
    'status' { & docker @ComposeArgs ps }
    'logs' { & docker @ComposeArgs logs --tail 100 }
    'backup' { Save-ServerBackup }
    'restore' {
        Assert-VolumeStopped
        if (-not $BackupFile -or -not $PSBoundParameters.ContainsKey('DataVolume') -or $DataVolume -eq $env:USOPP_DATA_VOLUME) { throw 'Supply -BackupFile and -DataVolume with a new empty volume name.' }
        $ArchivePath = (Resolve-Path -LiteralPath $BackupFile).Path
        $ArchiveRoot = Split-Path -Parent $ArchivePath
        if ($ArchiveRoot.Contains(',')) { throw 'Use a backup path without commas.' }
        & docker volume create $DataVolume | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create restore volume.' }
        & docker run --rm --network none --user 0 --entrypoint python --env USOPP_DATA_ROOT=/data --mount "type=volume,source=$DataVolume,target=/data" --mount "type=bind,source=$ArchiveRoot,target=/backup,readonly" $Config.image /opt/usopp/container_maintenance.pyc restore "/backup/$(Split-Path -Leaf $ArchivePath)"
        if ($LASTEXITCODE -ne 0) { throw 'Restore failed. The original volume and configuration were retained.' }
        $Config | Add-Member -NotePropertyName dataVolume -NotePropertyValue $DataVolume -Force
        $Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigFile -Encoding UTF8
        Write-Host 'Restore complete. Run start; the original volume is retained separately.'
    }
}
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose command failed.' }
