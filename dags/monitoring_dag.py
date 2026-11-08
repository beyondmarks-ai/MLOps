"""Production monitoring with explicit failures and durable retraining requests."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def monitor():
    from src.monitoring.service import check_monitoring

    return check_monitoring()


with DAG(
    "model_monitoring",
    start_date=datetime(2024, 1, 1),
    schedule="*/10 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["mlops"],
) as dag:
    PythonOperator(task_id="monitor_and_queue_retraining", python_callable=monitor)
