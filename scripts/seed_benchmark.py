"""Train the public benchmark in its own database and model registry name."""

import json
import os

from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "mysql":
        raise ValueError("Azure benchmark bootstrap expects the deployed MySQL server")
    os.environ["DATABASE_URL"] = url.set(database="churn_benchmark").render_as_string(
        hide_password=False
    )
    os.environ["MODEL_NAME"] = "MavenChurnModel"
    import mlflow

    from scripts.prepare_benchmark import download
    from src.data import store
    from src.training.lifecycle import run_cycle

    frame, manifest = download()
    store.initialize()
    store.add_dataset(frame, "public_maven_telecom_benchmark")
    manifest["unique_split_counts"] = {
        key: len(value) for key, value in store.training_data().items()
    }
    result = run_cycle()
    if "run_id" in result:
        with mlflow.start_run(run_id=result["run_id"]):
            mlflow.log_dict(manifest, "dataset_provenance.json")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
