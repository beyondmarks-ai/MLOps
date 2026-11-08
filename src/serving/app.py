"""Authenticated prediction and operations API with transactional storage."""

import asyncio
import contextlib
import hmac
import io
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import mlflow
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.security import APIKeyHeader

from src.data import store
from src.data.sources import MAX_UPLOAD_BYTES
from src.serving.model_loader import load_model_by_version, load_model_from_registry
from src.serving.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    PredictRequest,
    PredictResponse,
)

logger = logging.getLogger(__name__)
_loaded_model = None
_metrics = {"request_count": 0, "error_count": 0, "total_latency_ms": 0.0}
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key=Security(key_header)):
    keys = [os.getenv("API_KEY"), os.getenv("ADMIN_API_KEY")]
    if not any(keys):
        raise HTTPException(503, "API credentials are not configured")
    if not key or not any(hmac.compare_digest(key, allowed) for allowed in keys if allowed):
        raise HTTPException(401, "Invalid API key")


def authorize_admin(key=Security(key_header)):
    allowed = os.getenv("ADMIN_API_KEY")
    if not allowed or not key or not hmac.compare_digest(key, allowed):
        raise HTTPException(403, "Administrator key required")


def refresh_model():
    global _loaded_model
    name = os.getenv("MODEL_NAME", "ChurnModel")
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    versions = mlflow.tracking.MlflowClient().get_latest_versions(name, stages=["Production"])
    if not versions or (_loaded_model and str(versions[0].version) == str(_loaded_model.version)):
        return
    candidate = load_model_by_version(name, str(versions[0].version))
    sample = PredictRequest.model_config["json_schema_extra"]["example"]
    candidate.model.predict(pd.DataFrame([sample]))
    candidate.model.predict_proba(pd.DataFrame([sample]))
    _loaded_model = candidate  # In-flight requests retain their existing model reference.
    logger.info("Serving model version %s", candidate.version)


async def poll_models():
    while True:
        try:
            await asyncio.to_thread(refresh_model)
        except Exception:
            logger.exception("Model refresh failed; retaining current model")
        await asyncio.sleep(int(os.getenv("MODEL_REFRESH_SECONDS", "30")))


@asynccontextmanager
async def lifespan(app):
    global _loaded_model
    store.initialize()
    try:
        _loaded_model = load_model_from_registry()
    except Exception:
        logger.info("Waiting for first successful training run")
    task = asyncio.create_task(poll_models())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Churn MLOps", version="2.0.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/live")
def live():
    return {"status": "alive"}


@app.get("/sample-dataset", dependencies=[Depends(authorize_admin)])
def sample_dataset():
    from src.data.ingestion import generate_synthetic_churn_data

    return PlainTextResponse(
        generate_synthetic_churn_data(1000).to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample-churn.csv"},
    )


@app.get("/health", response_model=HealthResponse)
def health():
    model = _loaded_model
    if model is None:
        raise HTTPException(503, "Model not loaded")
    return HealthResponse(
        status="ok",
        model_name=model.name,
        model_version=str(model.version),
        model_stage=model.stage,
    )


@app.post("/predict", response_model=PredictResponse, dependencies=[Depends(authorize)])
def predict(request: PredictRequest):
    model = _loaded_model
    if model is None:
        raise HTTPException(503, "Model not loaded")
    start = time.perf_counter()
    prediction_id = str(uuid.uuid4())
    try:
        features = request.model_dump()
        frame = pd.DataFrame([features])
        prediction = int(model.model.predict(frame)[0])
        probability = float(model.model.predict_proba(frame)[0][1])
        store.save_prediction(prediction_id, features, prediction, probability, model.version)
        _metrics["request_count"] += 1
        _metrics["total_latency_ms"] += (time.perf_counter() - start) * 1000
        return PredictResponse(
            prediction_id=prediction_id,
            prediction=prediction,
            probability=probability,
            decision_threshold=float(getattr(model.model, "threshold", 0.5)),
            model_name=model.name,
            model_version=str(model.version),
        )
    except Exception:
        _metrics["error_count"] += 1
        logger.exception("Prediction failed")
        raise HTTPException(500, "Prediction failed") from None


@app.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(authorize)])
def feedback(request: FeedbackRequest):
    if not store.save_feedback(request.prediction_id, request.actual_label):
        raise HTTPException(404, "Prediction not found")
    return FeedbackResponse(
        status="ok", prediction_id=request.prediction_id, message="Feedback recorded"
    )


@app.post("/datasets", status_code=202, dependencies=[Depends(authorize_admin)])
async def upload_dataset(file: UploadFile = File(...)):
    try:
        contents = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Maximum dataset size is 10 MiB")
        try:
            frame = pd.read_csv(io.BytesIO(contents))
            dataset_id = await asyncio.to_thread(store.add_dataset, frame, "csv_upload")
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        return {
            "dataset_id": dataset_id,
            "status": "accepted",
            "message": "Training queued; the scheduler checks every five minutes.",
        }
    finally:
        await file.close()


@app.post("/retrain", status_code=202, dependencies=[Depends(authorize_admin)])
def retrain():
    request_id = store.enqueue("manual", f"manual-{int(time.time()) // 60}")
    return {"request_id": request_id, "status": "queued"}


@app.post("/rollback/{version}", dependencies=[Depends(authorize_admin)])
def rollback(version: int):
    from src.evaluation.promotion import promote_model

    candidate = load_model_by_version(version=str(version))
    sample = PredictRequest.model_config["json_schema_extra"]["example"]
    candidate.model.predict(pd.DataFrame([sample]))
    promote_model(str(version))
    refresh_model()
    return {"version": str(version), "status": "restored"}


@app.get("/status", dependencies=[Depends(authorize_admin)])
def status():
    return {
        **store.overview(),
        "last_result": store.get_state("last_result"),
        "serving_version": str(_loaded_model.version) if _loaded_model else None,
        "serving_model": _loaded_model.name if _loaded_model else None,
    }


@app.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(authorize)])
def metrics():
    return "\n".join(
        [
            f"churn_api_requests_total {_metrics['request_count']}",
            f"churn_api_errors_total {_metrics['error_count']}",
            f"churn_api_avg_latency_ms {_metrics['total_latency_ms'] / max(_metrics['request_count'], 1):.3f}",
            "",
        ]
    )
