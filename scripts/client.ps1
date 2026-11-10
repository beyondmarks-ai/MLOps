[CmdletBinding()]
param([ValidateSet('Install','Start','Stop','Open','Credentials','Status','Menu')][string]$Action = 'Menu')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path $PSScriptRoot -Parent
$PrivateDirectory = Join-Path $Root '.client'
$ConfigPath = Join-Path $PrivateDirectory '.env'

function New-Secret([switch]$Fernet) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    if ($Fernet) { return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_') }
    return ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
}

function Read-Config([string]$Path) {
    $config = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^([A-Z_]+)=(.*)$') { $config[$Matches[1]] = $Matches[2] }
        elseif ($line.Trim() -and -not $line.StartsWith('#')) { throw 'Invalid local configuration. Restore .client from your backup.' }
    }
    foreach ($name in @('API_KEY','ADMIN_API_KEY','MYSQL_PASSWORD','MYSQL_ROOT_PASSWORD','POSTGRES_PASSWORD','FERNET_KEY','AIRFLOW_SECRET_KEY','CLIENT_ADMIN_PASSWORD','DATABASE_URL','MODEL_NAME','APP_PORT','AIRFLOW_PORT','MLFLOW_PORT')) {
        if (-not $config.ContainsKey($name) -or -not $config[$name]) { throw "Local configuration is missing $name. Restore your configuration backup; passwords will not be replaced." }
    }
    foreach ($name in @('APP_PORT','AIRFLOW_PORT','MLFLOW_PORT')) {
        if ($config[$name] -notmatch '^\d{4,5}$' -or [int]$config[$name] -gt 65535) { throw "Invalid $name in local configuration." }
    }
    return $config
}

function Find-FreePort([int]$First) {
    for ($port = $First; $port -lt $First + 50; $port++) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
        try { $listener.Start(); return $port } catch [Net.Sockets.SocketException] {} finally { $listener.Stop() }
    }
    throw "No available loopback port near $First. Close conflicting applications."
}

function Invoke-Docker([string[]]$Arguments) {
    & $script:Docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE). Resolve the error above, then rerun Install. Your data and credentials are retained." }
}

function Compose([string[]]$Arguments) {
    Invoke-Docker (@('compose','--project-name','mlops-client','--env-file',$ConfigPath,'-f',"$Root\deploy\compose.azure.yml",'-f',"$Root\deploy\compose.local.yml") + $Arguments)
}

function Start-Docker {
    $script:Docker = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (-not (Test-Path -LiteralPath $script:Docker)) { throw 'Docker Desktop is missing. Run install-client.ps1 first.' }
    $info = Get-DockerOSType
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Starting Docker Desktop. Complete any first-launch terms or WSL prompts in Docker Desktop.'
        Start-Process -FilePath (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 5
            $info = Get-DockerOSType
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        }
        if (-not $ready) { throw 'Docker is not ready. Finish Docker Desktop setup, enable WSL 2/virtualization, restart Windows if requested, then rerun setup.' }
    }
    if ($info -ne 'linux') { throw 'Switch Docker Desktop to Linux containers, then retry.' }
    $version = & $script:Docker compose version --short
    if ($LASTEXITCODE -ne 0 -or ([version]($version.TrimStart('v').Split('-')[0])) -lt [version]'2.24.4') {
        throw 'Update Docker Desktop: Compose 2.24.4 or newer is required.'
    }
}

function Get-DockerOSType {
    $ErrorActionPreference = 'Continue'
    & $script:Docker info --format '{{.OSType}}' 2>$null
}

function Initialize-Config {
    if (Test-Path -LiteralPath $ConfigPath) { return }
    $volumes = & $script:Docker volume ls --filter label=com.docker.compose.project=mlops-client --format '{{.Name}}'
    if ($LASTEXITCODE -ne 0) { throw 'Could not check existing data volumes.' }
    if ($volumes) { throw 'Existing client data has no credentials file. Restore the original .client folder; setup will not replace database passwords.' }
    New-Item -ItemType Directory -Path $PrivateDirectory -Force | Out-Null
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544')) {
        $identity = [Security.Principal.SecurityIdentifier]::new($sid)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $PrivateDirectory -AclObject $acl
    $config = [ordered]@{}
    foreach ($name in @('API_KEY','ADMIN_API_KEY','MYSQL_PASSWORD','MYSQL_ROOT_PASSWORD','POSTGRES_PASSWORD','AIRFLOW_SECRET_KEY','CLIENT_ADMIN_PASSWORD')) { $config[$name] = New-Secret }
    $config.FERNET_KEY = New-Secret -Fernet
    $config.DATABASE_URL = "mysql+pymysql://mlops:$($config.MYSQL_PASSWORD)@mysql:3306/churn_client"
    $config.MODEL_NAME = 'ClientChurnModel'
    $config.APP_PORT = Find-FreePort 8088
    $config.AIRFLOW_PORT = Find-FreePort 8188
    $config.MLFLOW_PORT = Find-FreePort 5001
    $config.APP_HOST = ':80'
    $config.MLFLOW_ARTIFACT_ROOT = '/app/data/mlartifacts'
    foreach ($name in @('AZURE_STORAGE_ACCOUNT','SOURCE_CSV','SOURCE_API_URL','SOURCE_DATABASE_URL','SOURCE_SQL')) { $config[$name] = '' }
    $lines = foreach ($key in $config.Keys) { "$key=$($config[$key])" }
    # Publish only a complete file; an interrupted write must never become the next run's credentials.
    [IO.File]::WriteAllLines("$ConfigPath.tmp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath "$ConfigPath.tmp" -Destination $ConfigPath
}

function Write-ClientLinks($config) {
    $credentials = @"
MLOps LOCAL - PRIVATE CREDENTIALS (do not share or commit this file)
Dashboard: http://127.0.0.1:$($config.APP_PORT)
Paste this administrator key into the dashboard: $($config.ADMIN_API_KEY)
Prediction API key: $($config.API_KEY)
Airflow: http://127.0.0.1:$($config.AIRFLOW_PORT)
Airflow username: admin
Airflow password: $($config.CLIENT_ADMIN_PASSWORD)
MLflow: http://127.0.0.1:$($config.MLFLOW_PORT)
Database passwords and Fernet key: .env in this same private folder.
Keep a private backup of this folder AND your Docker volumes. Neither alone is a full backup.
These credentials belong to this installation. Azure/GitHub sign-in is not required.
"@
    [IO.File]::WriteAllText((Join-Path $PrivateDirectory 'CREDENTIALS.txt'),$credentials,[Text.UTF8Encoding]::new($false))
    $desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MLOps Local'
    New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    foreach ($item in @('Install','Start','Stop','Open','Credentials','Status')) {
        $link = $shell.CreateShortcut((Join-Path $desktop "$item.lnk"))
        $link.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        $link.Arguments = "-NoProfile -NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action $item"
        $link.WorkingDirectory = $Root
        $link.Save()
    }
}

function Wait-App($config) {
    $url = "http://127.0.0.1:$($config.APP_PORT)"
    Write-Host 'Checking the trained model and API...'
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try { $null = Invoke-RestMethod "$url/health" -TimeoutSec 5; $ready = $true; break } catch { Start-Sleep -Seconds 5 }
    }
    if (-not $ready) { throw 'The model is not ready. Run Install again to resume initial training. Use Status to inspect services.' }
    $null = Invoke-RestMethod "$url/status" -Headers @{'X-API-Key'=$config.ADMIN_API_KEY} -TimeoutSec 15
    $sample = @{age=35;tenure_months=24;monthly_charges=65.5;total_charges=1572;num_products=2;has_tech_support=1;has_online_security=0;has_backup=1;has_device_protection=0;is_senior_citizen=0;has_partner=1;has_dependents=0;contract_type='Month-to-month';payment_method='Electronic check';internet_service='Fiber optic'} | ConvertTo-Json
    $prediction = Invoke-RestMethod "$url/predict" -Method Post -ContentType 'application/json' -Body $sample -Headers @{'X-API-Key'=$config.API_KEY} -TimeoutSec 30
    if ($prediction.probability -lt 0 -or $prediction.probability -gt 1 -or -not $prediction.prediction_id) { throw 'Prediction self-check failed.' }
    Write-Host "Ready: $url (prediction check passed). Use Credentials to copy the administrator key."
}

function Main {
    if ($Action -eq 'Menu') {
        Write-Host 'MLOps Local: 1 Start | 2 Stop | 3 Open dashboard | 4 Credentials | 5 Status | 6 Resume install'
        $choice = Read-Host 'Choose 1-6'
        $actions = @{'1'='Start';'2'='Stop';'3'='Open';'4'='Credentials';'5'='Status';'6'='Install'}
        if (-not $actions.ContainsKey($choice)) { throw 'Choose a number from 1 to 6.' }
        $script:Action = $actions[$choice]
    }
    if ($Action -eq 'Install') { Start-Docker; Initialize-Config }
    if (-not (Test-Path -LiteralPath $ConfigPath)) { throw 'Run install-client.ps1 to set up this PC first.' }
    $config = Read-Config $ConfigPath
    if ($Action -eq 'Credentials') { Start-Process notepad.exe -ArgumentList "`"$PrivateDirectory\CREDENTIALS.txt`""; return }
    if ($Action -eq 'Open') { Start-Process "http://127.0.0.1:$($config.APP_PORT)"; return }
    if ($Action -ne 'Install') { Start-Docker }
    # Prevent unrelated Azure shell settings from overriding this installation's configuration.
    foreach ($key in $config.Keys) { [Environment]::SetEnvironmentVariable($key,$config[$key],'Process') }
    if ($Action -eq 'Stop') { Compose @('stop'); Write-Host 'Local backend stopped. Data is retained.'; return }
    if ($Action -eq 'Status') { Compose @('ps','--all'); return }
    Write-ClientLinks $config
    if ($Action -eq 'Install') {
        Write-Host 'Building dependencies and training the public demo. First setup can take 20-45 minutes.'
        Compose @('build','init','mlflow')
        Compose @('up','-d','--wait','--wait-timeout','300','mysql','postgres','mlflow')
        # Keep the scheduler from racing first-time training or a resumed bootstrap.
        Compose @('stop','scheduler')
        Compose @('run','--rm','--no-deps','client-setup')
    }
    Compose @('up','-d','--wait','--wait-timeout','300')
    Wait-App $config
    Start-Process "http://127.0.0.1:$($config.APP_PORT)"
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Main } catch { Write-Host "Local setup/control stopped: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
}
