"""Transactional dataset, prediction and retraining storage (MySQL in deployment)."""

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import (
    JSON,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    case,
    create_engine,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from src.data.ingestion import FEATURE_SCHEMA, TARGET_COLUMN
from src.data.validation import validate_schema

metadata = MetaData()
datasets = Table(
    "datasets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("source", String(255), nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("row_count", Integer, nullable=False),
)
samples = Table(
    "samples",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("dataset_id", String(64), nullable=False),
    Column("features", JSON, nullable=False),
    Column("label", Integer, nullable=False),
    Column("split", String(12), nullable=False),
)
predictions = Table(
    "predictions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("timestamp", String(32), index=True),
    Column("model_version", String(32), index=True),
    Column("features", JSON, nullable=False),
    Column("prediction", Integer),
    Column("probability", String(32)),
    Column("actual_label", Integer),
)
requests = Table(
    "training_requests",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("reason", String(80)),
    Column("created_at", String(32)),
    Column("status", String(16)),
    Column("run_id", String(64)),
    Column("attempts", Integer, nullable=False, default=0, server_default="0"),
)
state = Table(
    "pipeline_state",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("value", Text, nullable=False),
)


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


@lru_cache(maxsize=1)
def engine():
    url = os.getenv("DATABASE_URL", "sqlite:///data/application.db")
    if url.startswith("sqlite:"):
        Path("data").mkdir(exist_ok=True)
    return create_engine(url, pool_pre_ping=True, future=True)


def initialize():
    metadata.create_all(engine())
    with engine().begin() as conn:
        for key, value in [("training_lock", ""), ("last_training", "")]:
            if conn.execute(select(state.c.id).where(state.c.id == key)).first() is None:
                conn.execute(state.insert().values(id=key, value=value))


def enqueue(reason, request_id=None):
    request_id = request_id or str(uuid.uuid4())
    try:
        with engine().begin() as conn:
            conn.execute(
                requests.insert().values(
                    id=request_id, reason=reason, created_at=now(), status="pending"
                )
            )
    except IntegrityError:
        pass  # Repeated delivery of the same dataset/monitoring event is idempotent.
    return request_id


def add_dataset(df, source="upload"):
    result = validate_schema(df)
    if not result.passed:
        raise ValueError(result.summary())
    if (
        len(df) < 100
        or df[TARGET_COLUMN].value_counts().min() < 10
        or df[TARGET_COLUMN].nunique() != 2
    ):
        raise ValueError("Training datasets need at least 100 rows and 10 examples of each class")
    df = df[list(FEATURE_SCHEMA)].copy()
    records = json.loads(df.to_json(orient="records"))
    dataset_id = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    with engine().begin() as conn:
        if conn.execute(select(datasets.c.id).where(datasets.c.id == dataset_id)).first():
            return dataset_id
        conn.execute(
            datasets.insert().values(
                id=dataset_id, source=source[:255], created_at=now(), row_count=len(records)
            )
        )
        for record in records:
            label = int(record.pop(TARGET_COLUMN))
            # Numeric normalization makes identical CSV/JSON examples share the same split.
            for key, dtype in FEATURE_SCHEMA.items():
                if key in record and record[key] is not None and dtype != "object":
                    record[key] = float(record[key])
            sample_id = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
            previous = conn.execute(
                select(samples.c.label).where(samples.c.id == sample_id)
            ).first()
            if previous:
                if previous.label != label:
                    raise ValueError("Conflicting labels for identical features")
                continue
            bucket = int(sample_id[:8], 16) % 100
            split = "train" if bucket < 70 else "validation" if bucket < 85 else "holdout"
            conn.execute(
                samples.insert().values(
                    id=sample_id, dataset_id=dataset_id, features=record, label=label, split=split
                )
            )
        conn.execute(
            requests.insert().values(
                id=dataset_id, reason="new_data", created_at=now(), status="pending"
            )
        )
    return dataset_id


def training_data():
    with engine().connect() as conn:
        rows = conn.execute(select(samples)).mappings().all()
    return {
        split: pd.DataFrame(
            [{**r["features"], TARGET_COLUMN: r["label"]} for r in rows if r["split"] == split]
        ).replace({None: np.nan})
        for split in ("train", "validation", "holdout")
    }


def save_prediction(prediction_id, features, prediction, probability, version):
    with engine().begin() as conn:
        conn.execute(
            predictions.insert().values(
                id=prediction_id,
                timestamp=now(),
                model_version=str(version),
                features=features,
                prediction=int(prediction),
                probability=str(float(probability)),
            )
        )


def save_feedback(prediction_id, label):
    with engine().begin() as conn:
        result = conn.execute(
            update(predictions)
            .where(predictions.c.id == prediction_id)
            .values(actual_label=int(label))
        )
    return bool(result.rowcount)


def production_data(hours=24, version=None):
    query = select(predictions).where(
        predictions.c.timestamp
        >= (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds")
    )
    if version is not None:
        query = query.where(predictions.c.model_version == str(version))
    with engine().connect() as conn:
        rows = conn.execute(query).mappings().all()
    return pd.DataFrame(
        [
            {
                **r["features"],
                "prediction_id": r["id"],
                "timestamp": r["timestamp"],
                "model_version": r["model_version"],
                "prediction": r["prediction"],
                "probability": float(r["probability"]),
                "actual_label": r["actual_label"],
            }
            for r in rows
        ]
    )


def set_state(key, value):
    with engine().begin() as conn:
        exists = conn.execute(select(state.c.id).where(state.c.id == key)).first()
        if exists:
            conn.execute(update(state).where(state.c.id == key).values(value=json.dumps(value)))
        else:
            conn.execute(state.insert().values(id=key, value=json.dumps(value)))


def get_state(key, default=None):
    with engine().connect() as conn:
        value = conn.execute(select(state.c.value).where(state.c.id == key)).scalar()
    return json.loads(value) if value else default


def claim_training(run_id):
    """Serialize all DAGs, with a lease so a killed worker does not block forever."""
    with engine().begin() as conn:
        claimed = conn.execute(
            update(state)
            .where(state.c.id == "training_lock")
            .where(state.c.value < now())
            .values(value=(datetime.utcnow() + timedelta(hours=2)).isoformat())
        )
        if not claimed.rowcount:
            return False
        conn.execute(
            update(requests)
            .where(requests.c.status == "running")
            .values(status=case((requests.c.attempts >= 3, "failed"), else_="pending"))
        )
        result = conn.execute(
            update(requests)
            .where(requests.c.status == "pending")
            .where(requests.c.attempts < 3)
            .values(status="running", run_id=run_id, attempts=requests.c.attempts + 1)
        )
        if not result.rowcount:
            conn.execute(update(state).where(state.c.id == "training_lock").values(value=""))
            return False
    return True


def finish_training(run_id, success):
    with engine().begin() as conn:
        conn.execute(
            update(requests)
            .where(requests.c.run_id == run_id)
            .values(status="complete" if success else "failed")
        )
        if not success:
            conn.execute(
                update(requests)
                .where(requests.c.run_id == run_id)
                .where(requests.c.attempts < 3)
                .values(status="pending")
            )
        conn.execute(update(state).where(state.c.id == "training_lock").values(value=""))
    set_state("last_training", {"run_id": run_id, "success": success, "finished_at": now()})


def overview():
    with engine().connect() as conn:
        recent = [
            dict(row)
            for row in conn.execute(
                select(requests).order_by(requests.c.created_at.desc()).limit(10)
            ).mappings()
        ]
        files = [
            dict(row)
            for row in conn.execute(
                select(datasets).order_by(datasets.c.created_at.desc()).limit(10)
            ).mappings()
        ]
    return {
        "datasets": files,
        "training_requests": recent,
        "training": get_state("last_training"),
        "monitoring": get_state("monitoring"),
    }
