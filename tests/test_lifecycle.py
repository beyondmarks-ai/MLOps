"""Real training/artifact round-trip plus security, storage and failure checks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import mlflow
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.data import store
from src.data.ingestion import generate_synthetic_churn_data


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "app.db").as_posix())
    monkeypatch.setenv("API_KEY", "test-user")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin")
    store.engine.cache_clear()
    store.initialize()
    yield
    store.engine().dispose()
    store.engine.cache_clear()


def test_dataset_validation_deduplication_and_stable_splits(database):
    data = generate_synthetic_churn_data(500)
    data.loc[0, "monthly_charges"] = np.nan
    dataset_id = store.add_dataset(data)
    assert store.add_dataset(data) == dataset_id
    splits = store.training_data()
    assert sum(map(len, splits.values())) == 500
    original_counts = {k: len(v) for k, v in splits.items()}
    store.add_dataset(data.sample(frac=1))
    assert {k: len(v) for k, v in store.training_data().items()} == original_counts
    bad = data.copy()
    bad.loc[1, "churn"] = 4
    with pytest.raises(ValueError, match="Target"):
        store.add_dataset(bad)
    with store.engine().connect() as conn:
        assert len(conn.execute(select(store.datasets)).all()) == 2


def test_training_claim_is_exclusive_and_recovers(database):
    store.enqueue("test")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(store.claim_training, ["first", "second"]))
    assert sum(results) == 1
    winner = "first" if results[0] else "second"
    store.finish_training(winner, False)
    store.enqueue("retry")
    assert store.claim_training("third")


def test_failed_training_retries_are_bounded(database):
    request_id = store.enqueue("failure-test")
    for attempt in range(3):
        run_id = f"attempt-{attempt}"
        assert store.claim_training(run_id)
        store.finish_training(run_id, False)
    assert not store.claim_training("fourth")
    with store.engine().connect() as conn:
        row = conn.execute(select(store.requests).where(store.requests.c.id == request_id)).first()
    assert row.status == "failed" and row.attempts == 3


def test_expired_worker_exhausts_retry_budget(database):
    request_id = store.enqueue("worker-crash")
    for attempt in range(3):
        assert store.claim_training(f"crashed-{attempt}")
        with store.engine().begin() as conn:
            conn.execute(
                store.state.update().where(store.state.c.id == "training_lock").values(value="")
            )
    assert not store.claim_training("fourth")
    with store.engine().connect() as conn:
        row = conn.execute(select(store.requests).where(store.requests.c.id == request_id)).first()
    assert row.status == "failed" and row.attempts == 3


def test_promotion_recovers_zero_recall_without_reducing_auc():
    from types import SimpleNamespace

    from src.evaluation.promotion import compare_models

    labels = np.array([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.3, 0.4])
    champion = SimpleNamespace(
        predict=lambda _: np.zeros(4),
        predict_proba=lambda _: np.column_stack([1 - probabilities, probabilities]),
    )
    challenger = SimpleNamespace(
        predict=lambda _: labels,
        predict_proba=lambda _: np.column_stack([1 - probabilities, probabilities]),
    )
    assert compare_models(champion, challenger, np.zeros((4, 1)), labels)[2]
    assert not compare_models(challenger, champion, np.zeros((4, 1)), labels)[2]


@pytest.mark.integration
def test_real_upload_train_predict_feedback_monitor_and_rejection(database, tmp_path, monkeypatch):
    from src.monitoring import service
    from src.serving import app as serving
    from src.training import hyperparameter, lifecycle, train

    uri = "sqlite:///" + (tmp_path / "mlflow.db").as_posix()
    for module in (train, hyperparameter):
        monkeypatch.setattr(module, "MLFLOW_TRACKING_URI", uri)
    from src.evaluation import promotion

    monkeypatch.setattr(promotion, "MLFLOW_TRACKING_URI", uri)
    from src.serving import model_loader

    monkeypatch.setattr(model_loader, "MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("HPO_TRIALS", "1")
    monkeypatch.setenv("HPO_TIMEOUT", "30")
    monkeypatch.setenv("MIN_MODEL_AUC", "0")
    monkeypatch.setenv("MONITOR_MIN_SAMPLES", "10")
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment(
        train.EXPERIMENT_NAME, artifact_location=(tmp_path / "artifacts").as_uri()
    )
    data = generate_synthetic_churn_data(600)
    data.loc[0, "monthly_charges"] = np.nan

    async def idle_monitor():
        await asyncio.sleep(3600)

    with (
        patch.object(serving, "load_model_from_registry", side_effect=RuntimeError("untrained")),
        patch.object(serving, "poll_models", new=idle_monitor),
    ):
        with TestClient(serving.app) as client:
            assert client.get("/status").status_code == 403
            assert client.post("/predict", json={}).status_code == 401
            client.headers["X-API-Key"] = "test-user"
            assert client.post("/retrain").status_code == 403
            client.headers["X-API-Key"] = "test-admin"
            response = client.post(
                "/datasets", files={"file": ("data.csv", data.to_csv(index=False), "text/csv")}
            )
            assert response.status_code == 202, response.text
            result = lifecycle.run_cycle()
            assert result["decision"] == "promoted"
            assert len(result["candidates"]) == 3
            serving.refresh_model()
            assert client.get("/health").json()["model_version"] == result["version"]
            client.headers["X-API-Key"] = "test-user"
            for _i, row in generate_synthetic_churn_data(20, random_state=9).iterrows():
                label = int(row.pop("churn"))
                response = client.post("/predict", json=row.to_dict())
                assert response.status_code == 200, response.text
                assert response.json()["decision_threshold"] == result["decision_threshold"]
                prediction_id = response.json()["prediction_id"]
                feedback = client.post(
                    "/feedback", json={"prediction_id": prediction_id, "actual_label": label}
                )
                assert feedback.status_code == 200
            assert len(store.production_data().dropna(subset=["actual_label"])) == 20
            # Inject only the drift verdict; actual MLflow reference/version and DB reads are real.
            with patch.object(
                service, "generate_drift_reports", return_value=(str(tmp_path), True)
            ):
                monitored = service.check_monitoring()
                assert monitored["drift_detected"] and monitored["request_id"]
                assert service.check_monitoring()["request_id"] == monitored["request_id"]
            monkeypatch.setattr(promotion, "PROMOTION_AUC_DELTA", 1.0)
            rejected = lifecycle.run_cycle()
            assert rejected["decision"] == "rejected"
            serving.refresh_model()
            assert client.get("/health").json()["model_version"] == result["version"]
            with (
                patch.object(serving, "load_model_by_version", side_effect=RuntimeError("broken")),
                patch("mlflow.tracking.MlflowClient") as registry,
            ):
                registry.return_value.get_latest_versions.return_value = [
                    type("Version", (), {"version": "999"})()
                ]
                with pytest.raises(RuntimeError):
                    serving.refresh_model()
            assert client.get("/health").json()["model_version"] == result["version"]


def test_source_file_ingestion_and_missing_file_failure(database, tmp_path, monkeypatch):
    from src.data.sources import ingest_configured_source

    path = tmp_path / "source.csv"
    generate_synthetic_churn_data(300).to_csv(path, index=False)
    monkeypatch.setenv("SOURCE_CSV", str(path))
    assert len(ingest_configured_source()) == 1
    monkeypatch.setenv("SOURCE_CSV", str(tmp_path / "missing.csv"))
    with pytest.raises(FileNotFoundError):
        ingest_configured_source()


def test_database_and_https_sources(database, tmp_path, monkeypatch):
    import sqlite3
    from unittest.mock import MagicMock

    from src.data.sources import ingest_configured_source

    data = generate_synthetic_churn_data(300)
    source_uri = "sqlite:///" + (tmp_path / "source.db").as_posix()
    source = sqlite3.connect(tmp_path / "source.db")
    data.to_sql("churn_feed", source, index=False)
    source.close()
    monkeypatch.setenv("SOURCE_DATABASE_URL", source_uri)
    monkeypatch.setenv("SOURCE_SQL", "SELECT * FROM churn_feed")
    assert len(ingest_configured_source()) == 1
    monkeypatch.delenv("SOURCE_DATABASE_URL")
    monkeypatch.setenv("SOURCE_API_URL", "https://example.test/data")
    response = MagicMock()
    response.__enter__.return_value = response
    response.is_redirect = False
    response.iter_content.return_value = [data.to_json(orient="records").encode()]
    with patch("src.data.sources.requests.get", return_value=response):
        assert len(ingest_configured_source()) == 1
    monkeypatch.setenv("SOURCE_API_URL", "http://example.test/data")
    with pytest.raises(ValueError, match="HTTPS"):
        ingest_configured_source()


def test_real_drift_verdict_and_monitoring_failure(database, tmp_path):
    from src.monitoring.drift_detector import generate_drift_reports

    reference = generate_synthetic_churn_data(500)
    changed = reference.copy()
    for column in [
        "age",
        "tenure_months",
        "monthly_charges",
        "total_charges",
        "num_products",
        "has_tech_support",
        "has_online_security",
        "has_backup",
    ]:
        changed[column] = 1000
    _, drift = generate_drift_reports(reference, changed, reports_dir=str(tmp_path))
    assert drift
    with patch("evidently.report.Report.run", side_effect=RuntimeError("unavailable")):
        with pytest.raises(RuntimeError, match="unavailable"):
            generate_drift_reports(reference, changed, reports_dir=str(tmp_path))
