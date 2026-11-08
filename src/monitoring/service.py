"""Monitor the deployed model against its own reference data and labeled outcomes."""

import logging
import os
import time

import mlflow
import pandas as pd

from src.data import store
from src.evaluation.metrics import compute_full_metrics
from src.monitoring.drift_detector import generate_drift_reports

logger = logging.getLogger(__name__)


def check_monitoring():
    store.initialize()
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    client = mlflow.tracking.MlflowClient()
    versions = client.get_latest_versions(
        os.getenv("MODEL_NAME", "ChurnModel"), stages=["Production"]
    )
    if not versions:
        return {"status": "waiting_for_model"}
    version = versions[0]
    current = store.production_data(version=version.version)
    minimum = int(os.getenv("MONITOR_MIN_SAMPLES", "50"))
    if len(current) < minimum:
        result = {
            "status": "insufficient_samples",
            "samples": len(current),
            "minimum": minimum,
            "model_version": str(version.version),
            "checked_at": store.now(),
        }
        store.set_state("monitoring", result)
        return result
    reference_path = client.download_artifacts(version.run_id, "reference.csv")
    reference = pd.read_csv(reference_path)
    report_dir, drift = generate_drift_reports(
        reference,
        current,
        report_date=f"{str(version.version)}-{pd.Timestamp.utcnow().strftime('%Y%m%d-%H%M%S')}",
    )
    labeled = current.dropna(subset=["actual_label"])
    metrics, degradation = {}, False
    if len(labeled) >= minimum and labeled.actual_label.nunique() == 2:
        metrics = compute_full_metrics(
            labeled.actual_label.astype(int), labeled.prediction, labeled.probability
        )
        baseline = client.get_run(version.run_id).data.metrics["test_auc"]
        degradation = metrics["auc"] < baseline - float(os.getenv("PERFORMANCE_AUC_DROP", "0.1"))
    result = {
        "status": "checked",
        "model_version": str(version.version),
        "samples": len(current),
        "labeled_samples": len(labeled),
        "metrics": metrics,
        "drift_detected": bool(drift),
        "performance_degraded": bool(degradation),
        "report_dir": report_dir,
        "checked_at": store.now(),
    }
    if drift or degradation:
        # One automatic retraining request per deployed version per cooldown window.
        bucket = int(time.time()) // int(os.getenv("RETRAIN_COOLDOWN_SECONDS", "21600"))
        result["request_id"] = store.enqueue(
            "performance_drop" if degradation else "data_drift",
            f"monitor-{version.version}-{bucket}",
        )
    store.set_state("monitoring", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(check_monitoring())
