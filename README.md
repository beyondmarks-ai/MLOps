# MLOps: Customer Churn Prediction

An application that predicts whether a customer is likely to leave a service. It includes a dashboard, a prediction API, model training, model history, and scheduled monitoring.

**Installing for a client using the project owner's credentials? Get the private `Install-MLOps.cmd` file and double-click it.** This one file sets up the application on the client's Windows PC. No ZIP extraction, separate credentials file, Azure subscription, or separate Python installation is needed.

[Install on Windows](#install-on-windows) · [Start and stop](#start-and-stop-the-application) · [Troubleshooting](#troubleshooting) · [Owner instructions](#for-the-project-owner) · [Technical documentation](#technical-documentation)

## What the application does

1. **Checks customer data:** validates records, handles missing values, removes duplicates, and separates training, validation, and test data.
2. **Trains and compares models:** tries Random Forest, Gradient Boosting, and Logistic Regression with automatic parameter tuning. A candidate must pass evaluation checks before becoming the active model.
3. **Makes predictions:** returns a churn probability and a prediction through the dashboard or API.
4. **Monitors results:** runs scheduled checks and processes retraining requests while the backend is running. Actual customer outcomes can be submitted as feedback.

The installer trains a **public demonstration dataset of fictional telecom customers**, so you can try predictions immediately. Before using predictions for business decisions, validate a model with representative customer data in a separate, clean environment.

## Before you begin

| Requirement | What you need |
|---|---|
| Windows | Supported **Windows 11, 64-bit Intel/AMD**, version 23H2 or newer |
| Memory | **16 GB RAM recommended**; 8 GB minimum |
| Free space | At least **30 GB** on the Windows system drive and the installation drive |
| Internet | Required for initial downloads and the demo dataset |
| Permissions | Permission to approve Windows administrator prompts |
| Virtualization | Enabled in BIOS/UEFI; ask your IT administrator if needed |
| App Installer | Microsoft's **App Installer** must provide the `winget` command |

The script installs Git and Docker Desktop when missing, and requests WSL installation or update when necessary. **Python and the application dependencies run inside Docker**, so you do not install them individually on Windows.

Windows may request a restart. Docker Desktop may ask you to accept its terms and finish first-launch setup. Some businesses require a paid [Docker Desktop subscription](https://docs.docker.com/subscription/desktop-license/).

## Install on Windows

### 1. Get the private installer

Ask the project owner for **`Install-MLOps.cmd`** through a private, secure channel. Save it in a private folder on your PC. It contains the setup code and the owner's existing project credentials.

**GitHub's “Download ZIP” button downloads source code, not this private installer.** The owner's credentials are not published on GitHub.

You only need this **one file**. It prepares its own working files automatically. **Do not upload it to GitHub or put it in a shared folder:** its embedded credentials are encoded for packaging, not encrypted.

### 2. Run the installer

Double-click **`Install-MLOps.cmd`**.

If you prefer the command line, open **Windows PowerShell in that folder** and run:

```powershell
.\Install-MLOps.cmd
```

Use your normal Windows account and approve the individual administrator prompts when asked. The launcher uses a process-only PowerShell execution-policy setting; it does not change your system's execution policy.

During setup:

1. Approve the Git, Docker or WSL installation prompts.
2. If Windows requests a restart, restart and run **the same `Install-MLOps.cmd` again**.
3. Complete Docker Desktop's first-launch setup. Use the **WSL 2 backend and Linux containers**.
4. Wait for downloads, application setup, and initial model training. Allow approximately **20–45 minutes**, depending on your PC and connection.

The installer automatically:

- Prepares its working files in a protected folder under `%LOCALAPPDATA%\MLOps-Setup`.
- Clones this repository into `%LOCALAPPDATA%\MLOps`.
- Builds the containers and installs application dependencies.
- Creates local databases and configures Airflow and MLflow.
- Imports the owner's API keys, database passwords, Airflow password, and encryption keys.
- Downloads the checked demo dataset and trains the first model.
- Checks model readiness and an authenticated prediction.
- Creates desktop shortcuts and opens the dashboard when the checks pass.

If setup stops with an error, resolve the reported problem and run the same installer again. Reruns preserve existing credentials and data. An installation with different credentials is refused rather than having its database passwords overwritten.

### 3. Sign in and try a prediction

1. Open **Desktop → MLOps Local → Credentials**.
2. Copy the **administrator key** from the private credentials file.
3. Paste it into the dashboard's **Access key** field and click **Refresh status**.
4. In **3. Predict customer churn**, enter the customer details and click **Get prediction**.

The initial model is already trained on the demo dataset. You do not need to upload another sample CSV before trying a prediction.

The Credentials file also contains the Airflow login and exact service addresses. Airflow's username is **`admin`**; its password comes from the owner's private package.

| Service | Default address | Purpose |
|---|---|---|
| Dashboard and API | http://127.0.0.1:8088 | Use the application and make predictions |
| Airflow | http://127.0.0.1:8188 | View training and monitoring workflows |
| MLflow | http://127.0.0.1:5001 | View model versions, experiments, and results |

Setup chooses nearby free ports if these are busy. **Use the addresses in your Credentials file.** These services are accessible only from the installed PC; MLflow has no separate login in this local setup.

## Start and stop the application

Open the **MLOps Local** folder on your desktop:

| Shortcut | What it does |
|---|---|
| **Start** | Starts Docker and the backend, checks readiness, and opens the dashboard |
| **Stop** | Stops this project's backend containers and keeps the data and models |
| **Open** | Opens the dashboard when the backend is already running |
| **Credentials** | Opens the private login details |
| **Status** | Shows current container status |
| **Install** | Resumes application setup or unfinished initial training |

You can also double-click [Client-Control.cmd](Client-Control.cmd) in the installed project folder for a menu with these actions.

**Use Stop when you finish. Closing the browser or terminal does not stop the backend.** Containers left running can restart when Docker starts. Stop leaves Docker Desktop and other Docker projects alone; you can quit Docker Desktop afterward if nothing else needs it.

Local use does not consume Azure credits. Prediction works offline after setup, and scheduled jobs run only while the backend is running.

## Troubleshooting

| Problem | What to do |
|---|---|
| `winget` is missing | Install or update **App Installer** from Microsoft Store, then rerun setup. |
| Windows asks for a restart | Restart, then run the same installer again with the same credentials file. |
| Docker is not ready | Open Docker Desktop, finish setup, and select WSL 2/Linux containers. Enable virtualization if requested. |
| Setup fails or the model is not ready | Check the displayed error, available RAM, disk space and internet. Use **Status**, resolve the problem, then rerun **Install**. |
| A port is already in use | Close the conflicting application, or follow the port-change instructions in the detailed guide. |
| Credentials differ from an existing installation | Contact the owner to arrange a credential migration. Do not overwrite passwords or delete data to bypass the check. |
| Data exists but credentials are missing | Restore the original `.client` folder from your private backup. |

For WSL commands, recovery after a power failure, and more detail, see the [complete Windows setup guide](docs/client-install.md).

## Keep your data and credentials safe

Login details are stored in the installed project's **`.client`** folder. Databases and model artifacts are stored in Docker volumes named with the **`mlops-client_`** prefix.

Back up **both** the `.client` folder and these Docker volumes. Stop the backend before exporting the volumes. Credentials alone cannot restore the data. Automatic off-PC backups are not configured by this installer.

Docker's factory reset, deleting volumes, or running `docker compose down -v` can erase application data. Normal **Stop** preserves it.

Sharing the owner's credentials means those same keys can also access the owner's hosted application wherever they are accepted. It does not synchronize the installations' data or transfer the owner's Azure/GitHub account.

## For the project owner

To create the private client package, run this from your existing project checkout, where your private runtime configuration is available:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\client.ps1 -Action ExportCredentials -CredentialsFile .\.azure-local\runtime.env
```

The output is **`.client-transfer\single-file\Install-MLOps.cmd`**. Send just this file privately to the intended client. The export folder is excluded from Git and Docker builds. An existing export folder is not overwritten; retain or move the previous single-file export before creating another one. Older ZIP packages remain usable but are no longer needed for a new handoff.

The public repository contains **no credentials**. A fresh clone alone cannot recreate this private package without the owner's credential file.

<details>
<summary>Optional: install with new credentials instead</summary>

This option generates independent credentials. To use the owner's credentials, follow the private-package steps above.

Open Windows PowerShell and run:

```powershell
$installer = Join-Path $env:TEMP 'install-mlops-client.ps1'
Invoke-WebRequest 'https://raw.githubusercontent.com/beyondmarks-ai/MLOps/main/scripts/install-client.ps1' -OutFile $installer -UseBasicParsing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
```

</details>

## Developer setup and checks

Developers need **Python 3.11**. From the repository root on Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/ --cov=src --cov-fail-under=80
.\.venv\Scripts\ruff.exe check src/ dags/ tests/ scripts/
.\.venv\Scripts\ruff.exe format --check src/ dags/ tests/ scripts/
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-client.ps1
```

Airflow runs in its Linux container. The normal client installation does not require this developer setup.

Automated checks cover application tests, actual single-file CMD extraction and reruns, credential import, failure reporting, and a fresh Docker installation with login, prediction, stop/start, and data preservation. See [CI](https://github.com/beyondmarks-ai/MLOps/actions/workflows/ci.yml) and [client installer checks](https://github.com/beyondmarks-ai/MLOps/actions/workflows/client.yml). A clean Windows PC still needs a trial for its hardware, permissions, WSL setup, and Docker first-launch prompts.

## Technical documentation

The application uses **FastAPI**, **scikit-learn**, **Optuna**, **MLflow**, **Apache Airflow**, **MySQL**, **PostgreSQL**, **Caddy**, and **Docker**. Azure deployment is available separately.

| Guide | What it covers |
|---|---|
| [Windows client setup](docs/client-install.md) | Detailed installation, credential import, recovery, and local operation |
| [Azure operations](docs/azure-operations.md) | Cloud deployment, access, backups, and costs |
| [Current project report coverage](docs/report02-current-coverage.md) | Implemented report requirements and remaining limitations |
| [Validation evidence](docs/validation.md) | Evaluation and verification evidence |
| [Public benchmark](docs/benchmark.md) | Demo data, source, and model evaluation |
| [Original report comparison](docs/report02-coverage.md) | Gaps identified before implementation |

**Azure operators:** [Backend-Control.cmd](Backend-Control.cmd) controls the original Azure VM. Local clients use **Client-Control.cmd**. The GitHub **Deploy to Azure VM** workflow is run manually by an authorized operator; it is not part of local client installation.

| Folder | Contents |
|---|---|
| `src/data` | Validation, ingestion, storage, and data splits |
| `src/training` and `src/evaluation` | Training, tuning, evaluation, and model promotion |
| `src/serving` | Prediction API and dashboard |
| `src/monitoring` and `dags` | Monitoring and scheduled workflows |
| `scripts` and `deploy` | Installers, service controls, and deployment configuration |
| `tests` | Automated application and integration tests |
