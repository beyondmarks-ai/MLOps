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
function Read-InstallerBundle([string]$Path) {
    $parts = [IO.File]::ReadAllText($Path) -split '(?m)^:MLOPS_PAYLOAD\r?$',2
    Assert ($parts.Count -eq 2) 'Single-file payload marker missing'
    $runner = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($parts[1].Trim()))
    $parseErrors = $null
    $tokens = $null
    $null = [Management.Automation.Language.Parser]::ParseInput($runner,[ref]$tokens,[ref]$parseErrors)
    Assert (-not $parseErrors) 'Generated PowerShell payload has syntax errors'
    $encoded = [regex]::Match($runner,"FromBase64String\('([^']+)'\)").Groups[1].Value
    return ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json)
}
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
    $bundle = Read-InstallerBundle (Join-Path $package 'Install-MLOps.cmd')
    Assert ($bundle.installer -ceq [IO.File]::ReadAllText("$PSScriptRoot\install-client.ps1")) 'Embedded bootstrap differs from source'
    $extracted = Join-Path $testDirectory 'extracted.env'
    [IO.File]::WriteAllText($extracted,$bundle.credentials)
    $exported = Read-SharedCredentials $extracted
    Assert ($exported.Count -eq $CredentialNames.Count) 'Package contains unexpected configuration'
    Assert ($exported.CLIENT_ADMIN_PASSWORD -ceq $config.CLIENT_ADMIN_PASSWORD) 'Airflow credential alias changed the password'
    Assert (@(Get-ChildItem -LiteralPath $package).Count -eq 1) 'Export requires more than one client file'
    Assert ((Get-Acl -LiteralPath $package).AreAccessRulesProtected) 'Exported package has inherited public access'
    # Execute the real CMD extraction using a harmless bootstrap, including paths with shell metacharacters.
    $fakeBootstrap = @'
param([string]$CredentialsFile)
$ErrorActionPreference = 'Stop'
if ([IO.File]::ReadAllText($CredentialsFile) -cne 'test-credentials') { exit 8 }
if (-not (Get-Acl -LiteralPath $PSScriptRoot).AreAccessRulesProtected) { exit 9 }
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'verified.txt'),'passed')
exit 0
'@
    $singleFile = Join-Path $testDirectory 'Install & verify (test).cmd'
    [IO.File]::WriteAllText($singleFile,(New-SingleFileInstaller $fakeBootstrap 'test-credentials'))
    $savedLocalAppData = $env:LOCALAPPDATA
    try {
        $env:LOCALAPPDATA = $testDirectory
        '' | & $singleFile | Out-Null
        Assert ($LASTEXITCODE -eq 0) 'Single-file CMD failed to extract and invoke the bootstrap'
        '' | & $singleFile | Out-Null
        Assert ($LASTEXITCODE -eq 0) 'Single-file CMD failed on rerun'
        $checks = @(Get-ChildItem -LiteralPath (Join-Path $testDirectory 'MLOps-Setup') -Filter verified.txt -Recurse)
        Assert ($checks.Count -eq 1) 'Rerun did not reuse its private setup directory'
        $failureFile = Join-Path $testDirectory 'Fail.cmd'
        [IO.File]::WriteAllText($failureFile,(New-SingleFileInstaller 'param([string]$CredentialsFile); exit 7' 'test-credentials'))
        '' | & $failureFile | Out-Null
        Assert ($LASTEXITCODE -ne 0) 'Single-file CMD hid bootstrap failure'
    } finally { $env:LOCALAPPDATA = $savedLocalAppData }
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
    foreach ($name in @('.env','.env.tmp','docker.cmd','shared.env','extracted.env','Install & verify (test).cmd','Fail.cmd','package\Install-MLOps.cmd')) {
        $path = Join-Path $testDirectory $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
    $setupCache = Join-Path $testDirectory 'MLOps-Setup'
    if (Test-Path -LiteralPath $setupCache) {
        foreach ($folder in Get-ChildItem -LiteralPath $setupCache -Directory) {
            foreach ($name in @('install-client.ps1','credentials.env','verified.txt')) {
                $path = Join-Path $folder.FullName $name
                if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
            }
            Remove-Item -LiteralPath $folder.FullName
        }
        Remove-Item -LiteralPath $setupCache
    }
    $packagePath = Join-Path $testDirectory 'package'
    if (Test-Path -LiteralPath $packagePath) { Remove-Item -LiteralPath $packagePath }
    Remove-Item -LiteralPath $testDirectory
}
