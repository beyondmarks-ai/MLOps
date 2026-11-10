# Setup

For a new Windows client PC, follow [the automatic local setup guide](client-install.md).
It includes dependency installation, imported or fresh credentials, a trained public demo and
desktop controls. The manual development instructions below are separate.

See [README](../README.md) for local Python tests and Docker startup and [Azure operations](azure-operations.md) for the deployed environment, credentials, redeployment, backups and cost controls.

Generate secrets instead of using `.env.example` placeholders. A Fernet key can be generated with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Local tests use SQLite and temporary MLflow storage without Azure. Airflow itself must run in Linux/Docker. Azure's FastAPI endpoints require `X-API-Key`; public `/live` and `/health` endpoints report liveness and model readiness. The dashboard stores the entered key only in page memory.
