# Setup

See [README](../README.md) for local Python tests and Docker startup and [Azure operations](azure-operations.md) for the deployed environment, credentials, redeployment, backups and cost controls.

Generate secrets instead of using `.env.example` placeholders. A Fernet key can be generated with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Local tests use SQLite and temporary MLflow storage without Azure. Airflow itself must run in Linux/Docker. Azure's FastAPI endpoints require `X-API-Key`; public `/live` and `/health` endpoints report liveness and model readiness. The dashboard stores the entered key only in page memory.
