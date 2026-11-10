# Download this file, then run it in Windows PowerShell as your normal Windows user.
[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'MLOps'),
    [string]$CredentialsFile
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Run-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Correct the error above and rerun setup." }
}

try {
    if ($CredentialsFile) {
        $CredentialsFile = [IO.Path]::GetFullPath($CredentialsFile)
        if (-not (Test-Path -LiteralPath $CredentialsFile -PathType Leaf)) { throw 'The supplied private credentials file does not exist.' }
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'This installer supports x64 Windows only.'
    }
    $os = Get-CimInstance Win32_OperatingSystem
    if ([int]$os.BuildNumber -lt 22631 -or $os.ProductType -ne 1) {
        throw 'Use supported Windows 11 (23H2 or newer), with hardware virtualization enabled.'
    }
    $ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
    if ($ram -lt 7.5) { throw 'At least 8 GB RAM is required; 16 GB is recommended for training.' }
    if ($ram -lt 15) { Write-Warning '16 GB RAM is recommended. Close other apps during training.' }
    $InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory)
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($InstallDirectory).Substring(0,1))
    if ($drive.Free -lt 30GB) { throw 'Free at least 30 GB on the installation drive for images and data.' }
    $systemDrive = Get-PSDrive -Name $env:SystemDrive.Substring(0,1)
    if ($systemDrive.Free -lt 30GB) { throw 'Free at least 30 GB on the Windows system drive for Docker images and data.' }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'Install/update Microsoft App Installer from Microsoft Store, then rerun this script (winget is required).'
    }
    $ErrorActionPreference = 'Continue'
    $wslVersion = & wsl.exe --version 2>$null
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing WSL 2. Approve the Windows administrator prompt.'
        $wslInstall = Start-Process -FilePath "$env:SystemRoot\System32\wsl.exe" -ArgumentList '--install --no-distribution' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        if ($wslInstall.ExitCode -notin @(0,3010)) { throw 'WSL installation failed. Check that hardware virtualization is enabled and Windows is up to date.' }
        Write-Host 'WSL installation requested. Restart Windows, then rerun this same installer to continue.'
        exit 0
    }
    $wslText = ($wslVersion | Out-String).Replace([string][char]0,'')
    if ($wslText -notmatch '\b(\d+\.\d+\.\d+(?:\.\d+)?)\b') {
        throw 'Cannot verify the WSL version. Run wsl --update in an administrator terminal and retry.'
    }
    if ([version]$Matches[1] -lt [version]'2.1.5') {
        Write-Host 'Updating WSL for Docker Desktop. Approve the administrator prompt.'
        $wslUpdate = Start-Process -FilePath "$env:SystemRoot\System32\wsl.exe" -ArgumentList '--update' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        if ($wslUpdate.ExitCode -ne 0) { throw 'WSL update did not finish. Restart Windows if requested, then rerun setup.' }
    }
    # winget handles UAC; do not switch the entire installation to another Windows account.
    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        Run-Native winget.exe @('install','--id','Git.Git','--exact','--source','winget','--accept-source-agreements','--accept-package-agreements')
    }
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        Run-Native winget.exe @('install','--id','Docker.DockerDesktop','--exact','--source','winget','--accept-source-agreements')
    }
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH','User')
    $git = (Get-Command git.exe -ErrorAction Stop).Source
    if (-not (Test-Path -LiteralPath $InstallDirectory)) {
        Run-Native $git @('clone','https://github.com/beyondmarks-ai/MLOps.git',$InstallDirectory)
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $InstallDirectory '.git'))) {
            throw "Install directory already exists and is not the project repository: $InstallDirectory. Choose another -InstallDirectory."
        }
        $remote = & $git -C $InstallDirectory remote get-url origin
        if ($LASTEXITCODE -ne 0 -or $remote -notmatch '^https://github\.com/beyondmarks-ai/MLOps(?:\.git)?/?$') {
            throw 'Existing directory belongs to a different repository. Choose another -InstallDirectory.'
        }
        Write-Host 'Reusing the existing checkout without overwriting changes.'
    }
    $controller = Join-Path $InstallDirectory 'scripts\client.ps1'
    if (-not (Test-Path -LiteralPath $controller)) { throw 'This checkout predates the client installer. Update it before continuing.' }
    & $controller -Action Install -CredentialsFile $CredentialsFile
    if (-not $?) { throw 'Local setup did not finish. Rerun after resolving the reported error.' }
} catch {
    Write-Host "Setup stopped: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'If Docker requests WSL installation, follow its instructions (wsl --install --no-distribution in an administrator terminal), restart Windows if requested, and rerun this same script.'
    exit 1
}
