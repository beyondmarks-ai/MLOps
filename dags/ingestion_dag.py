"""Scheduled external ingestion; demo data is seeded explicitly, never substituted."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def ingest():
    from src.data.sources import ingest_configured_source

    return ingest_configured_source()


with DAG(
    "data_ingestion",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["mlops"],
) as dag:
    PythonOperator(task_id="ingest_validate_store", python_callable=ingest)
