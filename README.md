# MLOps ? Customer churn on Azure

An automated, authenticated churn prediction system using Python, FastAPI, scikit-learn, Optuna, MLflow, Apache Airflow, MySQL, Docker and Azure Blob Storage.

[Azure deployment and operations](docs/azure-operations.md) documents access, costs, recovery, and limitations. [Current report coverage](docs/report02-current-coverage.md) and [validation evidence](docs/validation.md) describe the completed deployment. [Original report comparison](docs/report02-coverage.md) records the gaps found before implementation.

## What works

- CSV uploads and operator-configured file, HTTPS JSON, and SQL sources with validation and missing-value imputation.
- Transactional MySQL datasets, predictions, actual-outcome feedback, and durable retraining requests.
- Stable, deduplicated train/validation/holdout splits; Optuna tuning across Random Forest, Gradient Boosting, and Logistic Regression.
- Complete preprocessing/classifier artifacts in MLflow; validation-based candidate selection and holdout-based promotion gates.
- Two FastAPI instances behind HTTPS, prediction/admin keys, model refresh with retention of the working model on failure, and administrator rollback.
- Airflow workflows for ingestion, weekly training, ten-minute monitoring, and five-minute processing of new-data/drift/performance requests.
- Version-specific drift references and labeled production metrics, cooldowns, bounded retries, private artifact storage and database backup scripts.

## Quick start

On this Windows computer, double-click [Backend-Control.cmd](Backend-Control.cmd) for **Start backend**, **Stop backend**, **Refresh**, and **Open App**. It uses your Azure CLI login. Start waits for application readiness; Stop deallocates the VM to stop compute billing. Closing the launcher does not stop the VM. Disk/IP/storage charges remain. See [on-demand operation](docs/azure-operations.md#on-demand-windows-launcher).

Python 3.11 is used for development and deployment. Airflow runs in its Linux container.

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ --cov=src --cov-fail-under=80
.venv/Scripts/ruff.exe check src/ dags/ tests/
```

For Docker, populate `.env` using `.env.example` with unique generated credentials and a Fernet key, then run `docker compose up -d --build`. The local default stores artifacts on a persistent Docker volume; the Azure deployment uses private Blob Storage and VM managed identity. `APP_HOST=localhost` uses Caddy's local CA; the public Azure hostname uses a publicly trusted certificate.

Open the dashboard, enter the administrator key, download the clearly marked synthetic sample or supply your own labeled CSV, and upload it. Airflow processes the queued training request. Predictions return `prediction_id`, which is used to submit actual outcomes to `/feedback`.

## Repository

| Location | Purpose |
|---|---|
| `src/data` | Validation, source adapters, durable storage, stable data splits |
| `src/features` | Imputation, scaling and encoding |
| `src/training/lifecycle.py` | Shared tuning, selection, registration and promotion workflow |
| `src/evaluation` | Classification metrics and promotion gates |
| `src/serving` | Authenticated API and dashboard |
| `src/monitoring` | Drift reports, labeled metrics and retraining requests |
| `dags` | Airflow schedules and task limits |
| `deploy` | HTTPS/container deployment and backups |
| `scripts` | Azure redeployment, synthetic bootstrap and backup upload |
| `tests` | Unit tests and real MLflow train/serve/feedback/rejection integration tests |

The initial Azure model is trained on synthetic demonstration data. A single VM is not cross-VM high availability. Real-world accuracy and large-data capacity need measurement on the intended workload. Source is published at [beyondmarks-ai/MLOps](https://github.com/beyondmarks-ai/MLOps). CI runs on pushes and pull requests; Azure deployment remains manual until the OIDC identity and repository variables in the operations guide are configured.
