param([string]$ResourceGroup = 'rg-churn-mlops', [string]$VmName = 'churn-mlops-vm')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.azure-local/id_ed25519')) { throw 'Deployment SSH key is missing.' }
$address = az vm show -d -g $ResourceGroup -n $VmName --query publicIps -o tsv
if ($LASTEXITCODE -ne 0) { throw 'Azure VM lookup failed; check az login.' }
$parsedAddress = $null
if (![System.Net.IPAddress]::TryParse($address, [ref]$parsedAddress)) { throw 'Expected one VM IP address.' }
@'
import tarfile
with tarfile.open('.azure-local/package.tar.gz','w:gz') as archive:
    for name in ['src','dags','docker','deploy','scripts','requirements.txt','.dockerignore']:
        archive.add(name,filter=lambda info: None if '__pycache__' in info.name else info)
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
scp -o UserKnownHostsFile=.azure-local/known_hosts -i .azure-local/id_ed25519 .azure-local/package.tar.gz "mlops@${address}:/opt/churn-mlops/package.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Package upload failed.' }
ssh -o UserKnownHostsFile=.azure-local/known_hosts -i .azure-local/id_ed25519 "mlops@$address" 'cd /opt/churn-mlops && tar -xzf package.tar.gz && sudo docker compose --env-file .env -f deploy/compose.azure.yml build && sudo docker compose --env-file .env -f deploy/compose.azure.yml up -d --wait --wait-timeout 240'
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; inspect container logs before retrying.' }
