"""Exercise the real local Compose stack on an isolated Linux CI runner."""

import base64
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This creates an isolated CI demo; run it only in GitHub Actions")
    private = Path(".client")
    private.mkdir(mode=0o700)  # Fail rather than overwrite another installation.
    config = {
        key: secrets.token_hex(32)
        for key in (
            "API_KEY",
            "ADMIN_API_KEY",
            "MYSQL_PASSWORD",
            "MYSQL_ROOT_PASSWORD",
            "POSTGRES_PASSWORD",
            "AIRFLOW_SECRET_KEY",
            "CLIENT_ADMIN_PASSWORD",
        )
    }
    config.update(
        FERNET_KEY=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        DATABASE_URL=f"mysql+pymysql://mlops:{config['MYSQL_PASSWORD']}@mysql:3306/churn_client",
        MODEL_NAME="ClientChurnModel",
        APP_HOST=":80",
        APP_PORT="8088",
        AIRFLOW_PORT="8188",
        MLFLOW_PORT="5001",
        MLFLOW_ARTIFACT_ROOT="/app/data/mlartifacts",
        AZURE_STORAGE_ACCOUNT="",
    )
    private.joinpath(".env").write_text("\n".join(f"{k}={v}" for k, v in config.items()))
    base = [
        "docker",
        "compose",
        "-p",
        "mlops-client",
        "--env-file",
        ".client/.env",
        "-f",
        "deploy/compose.azure.yml",
        "-f",
        "deploy/compose.local.yml",
    ]

    def compose(*args, capture=False):
        return subprocess.run(
            base + list(args), check=True, text=True, capture_output=capture
        ).stdout

    resolved = json.loads(compose("config", "--format", "json", capture=True))
    for service in resolved["services"].values():
        for port in service.get("ports", []):
            assert port["host_ip"] == "127.0.0.1", "Non-local port exposed"
            assert str(port["published"]) in {"8088", "8188", "5001"}

    def request(path, key=None, payload=None, port="8088"):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["X-API-Key"] = key
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data, headers)
        return urllib.request.urlopen(req, timeout=30)

    def health():
        for _ in range(60):
            try:
                with request("/health") as response:
                    return json.load(response)
            except (urllib.error.URLError, TimeoutError):
                time.sleep(5)
        raise RuntimeError("Model did not become healthy")

    compose("up", "-d", "--wait", "--wait-timeout", "300", "mysql", "postgres", "mlflow")
    compose("run", "--rm", "--no-deps", "client-setup")
    compose("up", "-d", "--wait", "--wait-timeout", "300")
    before = health()
    for key in (None, config["API_KEY"]):
        try:
            request("/status", key)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("Admin endpoint accepted missing/non-admin credentials")
    with request("/status", config["ADMIN_API_KEY"]) as response:
        status = json.load(response)
    assert len(status["datasets"]) == 1
    from src.serving.schemas import PredictRequest

    sample = PredictRequest.model_config["json_schema_extra"]["example"]
    with request("/predict", config["API_KEY"], sample) as response:
        prediction = json.load(response)
    assert 0 <= prediction["probability"] <= 1 and prediction["prediction_id"]
    with request("/health", port="5001") as response:
        assert response.status == 200
    # Verify the generated Airflow password, not merely that the webserver starts.
    compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "client-setup",
        "-c",
        "from airflow.www.app import cached_app\nimport os\n"
        "app=cached_app()\nwith app.app_context():\n"
        " assert app.appbuilder.sm.auth_user_db('admin', os.environ['CLIENT_ADMIN_PASSWORD'])",
    )
    compose("stop")
    compose("up", "-d", "--wait", "--wait-timeout", "300", "mysql", "postgres", "mlflow")
    compose("run", "--rm", "--no-deps", "client-setup")
    compose("up", "-d", "--wait", "--wait-timeout", "300")
    assert health()["model_version"] == before["model_version"], "Rerun retrained the model"
    with request("/status", config["ADMIN_API_KEY"]) as response:
        assert len(json.load(response)["datasets"]) == 1
    compose("stop")
    print("Local stack: initial training, credentials, prediction, stop/start and rerun passed.")


if __name__ == "__main__":
    main()
