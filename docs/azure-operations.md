# Azure deployment and operations

The deployed project uses the same validated training lifecycle for scheduled, uploaded-data and monitoring-triggered runs. See [current report coverage](report02-current-coverage.md) and [measured validation](validation.md). The old comparison in `report02-coverage.md` records the pre-implementation state.

## Resources

- Resource group: `rg-churn-mlops`, Central India.
- VM: `churn-mlops-vm`, `Standard_D4s_v3`, 4 vCPUs / 16 GiB RAM, Ubuntu 24.04, 64 GiB Standard SSD.
- Application: `https://churn-mlops-617db570.centralindia.cloudapp.azure.com`.
- Private storage account: `chmlops617db570`; `mlflow` artifacts and `backups` containers. Shared-key access and anonymous blob access are disabled. The VM's managed identity has Blob Data Contributor on this account.
- Key Vault: `kv-churn-617db570`; secret `runtime-config` backs up the runtime configuration under Azure RBAC.
- Only HTTPS/HTTP are open publicly. SSH is limited to the workstation IP used during deployment. MySQL, PostgreSQL and MLflow have no public host ports. Airflow binds to the VM loopback interface.

Docker Compose runs two FastAPI instances behind Caddy HTTPS, MySQL application storage, PostgreSQL metadata, MLflow, and Airflow LocalExecutor. This is a single-VM deployment; two API instances do not protect against a VM/region outage.

## Access and data

Keys are stored locally in ignored `.azure-local/runtime.env` and on the VM in `/opt/churn-mlops/.env` (mode 0600). Use `ADMIN_API_KEY` on the dashboard for uploads/status/retraining/rollback; `API_KEY` permits predictions, feedback, and metrics. Do not commit or paste these values into tickets or documentation. Rotate both files together, update the Key Vault `runtime-config` secret, and recreate affected containers when rotating credentials. Airflow username is `admin`; its password is `AIRFLOW_ADMIN_PASSWORD` in the same file.

The active model is `MavenChurnModel` version 1 in the `churn_benchmark` database, trained on the [public fictional telecom benchmark](benchmark.md). The original 3,000-row synthetic demo remains in database `churn` and registry `ChurnModel`. Use a fresh database and registry namespace before uploading real customer data; do not mix it into the benchmark. Download the synthetic sample CSV to see the required columns; the sample is for a separate demo cohort. `/predict` returns the ID required by `/feedback`. Actual labels must come from observed outcomes, not model predictions.

## Lifecycle

1. CSV upload or configured source validates data and stores it with a durable training request in one MySQL transaction. Sources support CSV, HTTPS JSON records, and operator-configured SQL; use a read-only database account for a source. Network destinations and SQL are not accepted from API callers.
2. Airflow polls training requests every five minutes. The database lease and DAG limits serialize training. Dataset hashes deduplicate rows and assign stable train/validation/holdout splits, preventing an old holdout row moving into training on a later run.
3. Optuna tunes Random Forest, Gradient Boosting and Logistic Regression using the same training/validation split. Validation AUC selects among candidates with nonzero churn recall; Random Forest and Logistic Regression use balanced class weights. Each logged model contains preprocessing, its classifier, and a threshold selected by validation F1. F1 is a demonstration objective, not an agreed business cost. The API returns the threshold used.
4. The candidate must have nonzero holdout recall and pass the configured minimum holdout AUC (default 0.55). It normally must exceed the champion AUC by more than 0.01. If the champion detects no churn, a candidate with positive recall and no AUC regression may replace it. A serialized-model round-trip is checked before promotion. These are demonstration defaults, not guarantees of business suitability.
5. Both API instances poll the registry every 30 seconds, validate a new artifact before swapping references, and retain the working model if loading fails. In-flight requests keep their original model. `POST /rollback/{version}` is administrator-only and restores a validated previous version.
6. Monitoring runs every ten minutes against the deployed model's own reference artifact and recent predictions for that version. Fewer than 50 samples produce an explicit insufficient-data status. Labeled windows with both classes produce accuracy, precision, recall, F1 and AUC. Drift or an AUC drop exceeding 0.1 queues retraining, at most once per version per six-hour cooldown window.

The stable holdout is repeatedly used as a deployment gate. Use a separate untouched/time-based benchmark for claims about final real-world accuracy. Data processing is in-memory pandas/scikit-learn, not distributed big-data processing.

## Commands

### On-demand Windows launcher

Double-click [Backend-Control.cmd](../Backend-Control.cmd) from this repository. The launcher runs locally, so it works while the Azure VM is off. It requires the existing `.venv` Python environment (including standard-library Tkinter), Azure CLI and a valid `az login` with permission on this VM. It explicitly targets this project's subscription and VM; it does not need the application API keys.

| Button | Result |
|---|---|
| Start backend | Starts the VM and waits for HTTPS `/health` to report the model ready. Allow several minutes. |
| Stop backend | Confirms taking the app offline, then deallocates the VM and waits for Azure's confirmation. |
| Refresh | Reads VM state and application readiness. Reports allocated-but-stopped VMs as still billable. |
| Open App | Opens the existing dashboard in your default browser. Start first if stopped. |

Closing the launcher does not stop the VM. Stop it when finished. Deallocation keeps databases, model artifacts and the static public address, while removing compute charges; disk, public IP and storage charges remain. All services share this VM, so the dashboard, predictions, training, monitoring and daily backup cron are unavailable while it is stopped. Docker is enabled at boot and the existing containers restart automatically. Interrupted training can wait for its two-hour database lease to expire before retrying. Run a backup before stopping after important data changes; the scheduled backup cannot run while powered off.

This provides manual on-demand operation, not automatic shutdown after inactivity. The Azure Portal VM Start/Stop controls are an alternative if this workstation is unavailable. No separate hosted control service or new Azure resource is required.

From the repository in PowerShell:

```powershell
# Validate changes before deployment.
.venv/Scripts/python.exe -m pytest tests/ --cov=src --cov-fail-under=80
.venv/Scripts/ruff.exe check src/ dags/ tests/
.venv/Scripts/ruff.exe format --check src/ dags/ tests/
./scripts/deploy.ps1

# Stop compute charges between demonstrations. Disk/storage charges remain.
az vm deallocate -g rg-churn-mlops -n churn-mlops-vm
az vm start -g rg-churn-mlops -n churn-mlops-vm

# Private Airflow access while this tunnel is open.
ssh -i .azure-local/id_ed25519 -o UserKnownHostsFile=.azure-local/known_hosts -L 8080:127.0.0.1:8080 mlops@20.193.227.84
```

On the VM, from `/opt/churn-mlops`:

```bash
sudo docker compose --env-file .env -f deploy/compose.azure.yml ps
sudo docker compose --env-file .env -f deploy/compose.azure.yml logs --tail=100 scheduler api mlflow
sudo bash deploy/backup.sh
sudo bash deploy/verify-backup.sh # restores the latest MySQL dump into an isolated temporary database
```

Backups dump MySQL and PostgreSQL transactionally where supported, compress them, and upload them to private Blob Storage using managed identity. Artifacts already live in Blob Storage. A root cron job runs backups daily at 02:15 UTC. Blob lifecycle retention is 14 days for backups, with 7-day soft delete. The runtime `.env` is backed up separately in Key Vault; database dumps do not contain it. The MySQL restore check passed with 3,000 training samples. The PostgreSQL dump was uploaded but has not been restore-tested. Restore into an isolated database first, validate counts and predictions, and only then switch the application connection string. Never run `docker compose down -v` against this deployment: that removes database volumes.

## Cost and delivery limits

The checked Azure public Linux compute rate was US$0.21/hour (about US$153.30 per 730-hour month), excluding disks, IP, storage, network, taxes and any subscription discounts. Credit balance and expiration could not be inferred from the enabled subscription. Deallocate when the demo is not needed; budgets alone do not stop resources.

The project is published at `https://github.com/beyondmarks-ai/MLOps`; CI runs on pushes and pull requests. The manual Azure CLI deployment also works independently of GitHub.

### GitHub OIDC deployment

Open **Actions ? Deploy to Azure VM ? Run workflow**, select `main`, and run it. It installs dependencies, runs lint/tests, signs into Azure using a short-lived GitHub OIDC token, and deploys the exact selected commit through Azure VM Run Command. Both API containers and public HTTPS must pass health checks before success is reported. An already running VM remains running; a stopped VM is temporarily started and then deallocated, including on normal deployment failure. No stored Azure password, SSH key, or client secret is sent to GitHub.

Configured identity: `id-github-churn-deploy` in `rg-churn-mlops`, client ID `ffccd29e-54bd-461c-8a78-4899baaac798`. Federated credential `github-main` trusts issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and exact subject `repo:beyondmarks-ai@250069932/MLOps@1450067870:ref:refs/heads/main`. This is the exact subject emitted by GitHub, including immutable owner/repository IDs. Other branches cannot authenticate with it.

Custom role `Churn MLOps GitHub deployer` is assigned only on `churn-mlops-vm`. It permits VM read, instance-view read, start, deallocate and Run Command. It cannot modify RBAC or other Azure resources. Run Command executes as root on this VM, so protect write access to `main`: trusted deployment code can access the VM's runtime configuration and managed identity.

Repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` hold public identifiers, not secrets. The workflow is deliberately manual so each source push does not start billable compute. It serializes deployment runs. If a runner is force-killed, loses Azure connectivity, or shutdown itself fails, verify the VM state with the Windows launcher and stop it if needed; `finally` cleanup cannot guarantee shutdown under those conditions.

Implementation: `.github/workflows/cd.yml`, `scripts/github_deploy.py`, `deploy/github-release.sh`. Guest script completion is checked explicitly because Run Command can return CLI success for a failed shell command. Checkout files retain the `mlops` owner so the existing SSH deployment path continues to work. The original source repository remains the local `upstream` remote.


Remaining operational limits: no cross-VM high availability, no independently verified uptime SLA, and no guarantee of accuracy on real customer data. Scale/load and backup checks are demonstration evidence, not a production certification.
