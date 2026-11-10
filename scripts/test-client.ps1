# Pure helper/ACL checks: never installs software or starts Docker.
$ErrorActionPreference = 'Stop'
foreach ($file in @('client.ps1','install-client.ps1')) {
    $parseErrors = $null
    $tokens = $null
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors) { throw ($parseErrors | Out-String) }
}
. "$PSScriptRoot\client.ps1"
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$first = New-Secret
Assert ($first -match '^[0-9a-f]{64}$') 'Invalid secret format'
Assert ($first -ne (New-Secret)) 'Secrets must be independent'
$fernet = New-Secret -Fernet
Assert ([Convert]::FromBase64String($fernet.Replace('-','+').Replace('_','/')).Length -eq 32) 'Invalid Fernet key'
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8088)
try {
    $listener.Start()
    Assert ((Find-FreePort 8088) -ne 8088) 'Busy port was selected'
} finally { $listener.Stop() }
$testDirectory = Join-Path $env:TEMP ('mlops-client-test-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testDirectory | Out-Null
$script:PrivateDirectory = $testDirectory
$script:ConfigPath = Join-Path $testDirectory '.env'
# A fake docker command supports the read-only volume inventory needed by Initialize-Config.
$fakeDocker = Join-Path $testDirectory 'docker.cmd'
[IO.File]::WriteAllText($fakeDocker,"@echo off`r`nexit /b 0`r`n")
$script:Docker = $fakeDocker
try {
    Initialize-Config
    $before = [IO.File]::ReadAllText($ConfigPath)
    Initialize-Config
    Assert ($before -ceq [IO.File]::ReadAllText($ConfigPath)) 'Rerun changed credentials'
    $config = Read-Config $ConfigPath
    Assert ($config.API_KEY -ne $config.ADMIN_API_KEY) 'API and admin keys match'
    Assert ((Get-Acl -LiteralPath $testDirectory).AreAccessRulesProtected) 'Credentials inherited public permissions'
    $source = Join-Path $testDirectory 'shared.env'
    $sharedLines = foreach ($key in $CredentialNames) {
        $sourceKey = if ($key -eq 'CLIENT_ADMIN_PASSWORD') { 'AIRFLOW_ADMIN_PASSWORD' } else { $key }
        "$sourceKey=$($config[$key])"
    }
    $sharedLines += @('DATABASE_URL=mysql://remote-host/owner','AZURE_STORAGE_ACCOUNT=owner-account')
    [IO.File]::WriteAllLines($source,[string[]]$sharedLines)
    $script:CredentialsFile = $source
    Initialize-Config
    Assert ($before -ceq [IO.File]::ReadAllText($ConfigPath)) 'Matching imported credentials changed an existing install'
    Remove-Item -LiteralPath $ConfigPath
    Initialize-Config
    $imported = Read-Config $ConfigPath
    foreach ($key in $CredentialNames) { Assert ($imported[$key] -ceq $config[$key]) "Import changed $key" }
    Assert ($imported.DATABASE_URL -ceq "mysql+pymysql://mlops:$($config.MYSQL_PASSWORD)@mysql:3306/churn_client") 'Owner database address was copied'
    Assert ($imported.AZURE_STORAGE_ACCOUNT -eq '') 'Owner Azure configuration was copied'
    $package = Join-Path $testDirectory 'package'
    Export-ClientPackage $source $package
    $exported = Read-SharedCredentials (Join-Path $package 'credentials.env')
    Assert ($exported.Count -eq $CredentialNames.Count) 'Package contains unexpected configuration'
    Assert ($exported.CLIENT_ADMIN_PASSWORD -ceq $config.CLIENT_ADMIN_PASSWORD) 'Airflow credential alias changed the password'
    Assert (Test-Path -LiteralPath (Join-Path $package 'MLOps-Client-Setup.zip')) 'Private archive was not created'
    Assert ((Get-Acl -LiteralPath $package).AreAccessRulesProtected) 'Exported package has inherited public access'
    $snapshot = [IO.File]::ReadAllText($ConfigPath)
    [IO.File]::WriteAllLines($source,[string[]]($sharedLines | ForEach-Object { if ($_ -match '^API_KEY=') { 'API_KEY=different-value' } else { $_ } }))
    $rejected = $false
    try { Initialize-Config } catch { $rejected = $true }
    Assert $rejected 'Import overwrote existing credentials'
    Assert ($snapshot -ceq [IO.File]::ReadAllText($ConfigPath)) 'Rejected import changed configuration'
    foreach ($badLines in @(@('API_KEY=only-one-key'), @($sharedLines + 'API_KEY=duplicate'), @($sharedLines | ForEach-Object { if ($_ -match '^API_KEY=') { 'API_KEY=$UNSAFE_EXPANSION' } else { $_ } }))) {
        [IO.File]::WriteAllLines($source,[string[]]$badLines)
        $rejected = $false
        try { Read-SharedCredentials $source | Out-Null } catch { $rejected = $true }
        Assert $rejected 'Incomplete, duplicate or interpolated credentials were accepted'
    }
    $script:CredentialsFile = ''
    [IO.File]::WriteAllText($ConfigPath,'APP_PORT=8088')
    $rejected = $false
    try { Read-Config $ConfigPath | Out-Null } catch { $rejected = $true }
    Assert $rejected 'Partial credentials accepted'
    Remove-Item -LiteralPath $ConfigPath
    [IO.File]::WriteAllText($fakeDocker,"@echo off`r`necho mlops-client_mysql-data`r`nexit /b 0`r`n")
    $rejected = $false
    try { Initialize-Config } catch { $rejected = $true }
    Assert $rejected 'Existing data with missing credentials was not protected'
    Write-Host 'Client script checks passed.'
} finally {
    # Remove only these explicitly named temporary files, never a recursive computed path.
    foreach ($name in @('.env','.env.tmp','docker.cmd','shared.env','package\credentials.env','package\install-client.ps1','package\Install-MLOps.cmd','package\READ-ME.txt','package\MLOps-Client-Setup.zip')) {
        $path = Join-Path $testDirectory $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
    $packagePath = Join-Path $testDirectory 'package'
    if (Test-Path -LiteralPath $packagePath) { Remove-Item -LiteralPath $packagePath }
    Remove-Item -LiteralPath $testDirectory
}
