"""Durable new-data/drift queue consumed every five minutes by Airflow."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def retrain():
    from src.training.lifecycle import run_cycle

    return run_cycle()


with DAG(
    "retraining_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=1),
    tags=["mlops"],
) as dag:
    PythonOperator(
        task_id="retrain_evaluate_promote",
        python_callable=retrain,
        execution_timeout=timedelta(minutes=55),
    )
