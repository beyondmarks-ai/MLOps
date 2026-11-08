"""Exercise the deployed API with clearly synthetic customers; never prints keys."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from dotenv import dotenv_values

from src.data.ingestion import generate_synthetic_churn_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".azure-local/runtime.env")
    parser.add_argument(
        "--drift-demo", action="store_true", help="Send unlabeled shifted synthetic features"
    )
    args = parser.parse_args()
    config = dotenv_values(args.config)
    base = "https://" + config["APP_HOST"]
    headers = {"X-API-Key": config["API_KEY"]}
    assert requests.get(base + "/live", timeout=20).status_code == 200
    assert requests.post(base + "/predict", json={}, timeout=20).status_code == 401
    assert requests.post(base + "/retrain", headers=headers, timeout=20).status_code == 403
    frame = generate_synthetic_churn_data(100 if args.drift_demo else 50, random_state=97)
    if args.drift_demo:
        frame["age"] = 75
        frame["tenure_months"] = 1
        frame["monthly_charges"] = 500.0 + np.arange(len(frame))
        frame["total_charges"] = frame.monthly_charges
        frame["num_products"] = 15
        frame["has_tech_support"] = 1
        frame["has_online_security"] = 1
        frame["has_backup"] = 1

    def predict(row):
        label = int(row.pop("churn"))
        started = time.perf_counter()
        response = requests.post(base + "/predict", headers=headers, json=row, timeout=30)
        response.raise_for_status()
        elapsed = (time.perf_counter() - started) * 1000
        result = response.json()
        assert 0 <= result["probability"] <= 1
        if not args.drift_demo:
            feedback = requests.post(
                base + "/feedback",
                headers=headers,
                json={"prediction_id": result["prediction_id"], "actual_label": label},
                timeout=20,
            )
            feedback.raise_for_status()
        return elapsed

    with ThreadPoolExecutor(max_workers=4) as pool:
        latency = list(pool.map(predict, frame.to_dict(orient="records")))
    result = {
        "scenario": "unlabeled_synthetic_drift"
        if args.drift_demo
        else "synthetic_prediction_feedback",
        "requests": len(latency),
        "concurrency": 4,
        "client_p50_ms": round(float(np.percentile(latency, 50)), 2),
        "client_p95_ms": round(float(np.percentile(latency, 95)), 2),
    }
    Path(".azure-local").mkdir(exist_ok=True)
    Path(f".azure-local/{result['scenario']}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
