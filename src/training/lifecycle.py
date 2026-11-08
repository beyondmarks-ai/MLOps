"""One train/tune/evaluate/promote path shared by scheduled and event-driven runs."""

import logging
import os
import tempfile
import uuid
from pathlib import Path

import mlflow

from src.data import store
from src.data.ingestion import TARGET_COLUMN
from src.evaluation.metrics import compute_full_metrics
from src.evaluation.promotion import compare_models, load_production_model, promote_model
from src.features.engineering import fit_preprocessor, transform_features
from src.training.hyperparameter import optimize_hyperparameters
from src.training.train import SUPPORTED_MODELS, get_default_params, register_model, train_model

logger = logging.getLogger(__name__)


def run_cycle():
    store.initialize()
    cycle_id = str(uuid.uuid4())
    if not store.claim_training(cycle_id):
        return {"decision": "no_pending_work"}
    try:
        # Include actual outcomes only; predictions are never treated as truth.
        feedback = store.production_data(hours=24 * 365)
        splits = store.training_data()
        if not feedback.empty:
            labeled = feedback.dropna(subset=["actual_label"])
            # Existing examples keep their split; fresh feedback is assigned by the same hash.
            if (
                len(labeled) >= 100
                and labeled.actual_label.nunique() == 2
                and labeled.actual_label.value_counts().min() >= 10
            ):
                from src.data.ingestion import FEATURE_SCHEMA

                df = labeled.rename(columns={"actual_label": TARGET_COLUMN})[list(FEATURE_SCHEMA)]
                store.add_dataset(df, "production_feedback")
                splits = store.training_data()
        for name, df in splits.items():
            if df.empty or df[TARGET_COLUMN].nunique() != 2:
                raise ValueError(f"{name} split must contain examples of both classes")
        train, validation, holdout = (splits[k] for k in ("train", "validation", "holdout"))
        preprocessor = fit_preprocessor(train)
        X_train, y_train = transform_features(train, preprocessor)
        X_val, y_val = transform_features(validation, preprocessor)
        candidates = []
        for model_type in SUPPORTED_MODELS:
            params = get_default_params(model_type)
            params.update(
                optimize_hyperparameters(
                    X_train,
                    y_train,
                    X_val,
                    y_val,
                    model_type=model_type,
                    n_trials=int(os.getenv("HPO_TRIALS", "5")),
                    timeout=int(os.getenv("HPO_TIMEOUT", "120")),
                )
            )
            model, run_id, metrics = train_model(
                train.drop(columns=TARGET_COLUMN),
                train[TARGET_COLUMN],
                validation.drop(columns=TARGET_COLUMN),
                validation[TARGET_COLUMN],
                model_type=model_type,
                params=params,
                tags={"cycle_id": cycle_id},
            )
            candidates.append((model, run_id, metrics, model_type))
        eligible = [candidate for candidate in candidates if candidate[2]["recall"] > 0]
        if not eligible:
            raise ValueError(
                "No candidate detects churn in validation; review labels and class balance"
            )
        model, run_id, val_metrics, model_type = max(eligible, key=lambda c: c[2]["auc"])
        X_test, y_test = holdout.drop(columns=TARGET_COLUMN), holdout[TARGET_COLUMN]
        test_metrics = compute_full_metrics(
            y_test, model.predict(X_test), model.predict_proba(X_test)[:, 1]
        )
        comparison = [{"model": c[3], "run_id": c[1], **c[2]} for c in candidates]
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})
            mlflow.log_dict(comparison, "model_comparison.json")
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "reference.csv"
                train.to_csv(path, index=False)
                mlflow.log_artifact(str(path))
        version = register_model(run_id, val_metrics=val_metrics)
        if version is None:
            raise RuntimeError("Model registration failed")
        client = mlflow.tracking.MlflowClient()
        versions = client.get_latest_versions(
            os.getenv("MODEL_NAME", "ChurnModel"), stages=["Production"]
        )
        champion = load_production_model() if versions else None
        accepted = (
            test_metrics["auc"] >= float(os.getenv("MIN_MODEL_AUC", "0.55"))
            and test_metrics["recall"] > 0
        )
        if champion is not None:
            _, _, improved = compare_models(champion, model, X_test, y_test)
            accepted = accepted and improved
        # Round-trip the real artifact before making it discoverable by the API.
        reloaded = mlflow.sklearn.load_model(
            f"models:/{os.getenv('MODEL_NAME', 'ChurnModel')}/{version}"
        )
        reloaded.predict(X_test.iloc[:1])
        if accepted:
            promote_model(version)
        result = {
            "decision": "promoted" if accepted else "rejected",
            "version": str(version),
            "model": model_type,
            "run_id": run_id,
            "test_metrics": test_metrics,
            "candidates": comparison,
            "previous_version": str(versions[0].version) if versions else None,
        }
        store.set_state("last_result", result)
        store.finish_training(cycle_id, True)
        return result
    except Exception:
        store.finish_training(cycle_id, False)
        logger.exception("Training failed; current production model retained")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_cycle())
