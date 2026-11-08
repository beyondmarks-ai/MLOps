"""Explicitly seed a reproducible synthetic demonstration dataset."""

from src.data import store
from src.data.ingestion import generate_synthetic_churn_data

if __name__ == "__main__":
    store.initialize()
    dataset_id = store.add_dataset(generate_synthetic_churn_data(3000), "synthetic_demo")
    print(f"Synthetic demo dataset accepted: {dataset_id}")
