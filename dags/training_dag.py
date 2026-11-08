"""Weekly candidate refresh, using the same guarded pipeline as event retraining."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def train(**context):
    from src.data import store
    from src.training.lifecycle import run_cycle

    store.initialize()
    store.enqueue("scheduled", context["run_id"][-64:])
    return run_cycle()


with DAG(
    "training_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@weekly",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    dagrun_timeout=timedelta(hours=1),
    tags=["mlops"],
) as dag:
    PythonOperator(
        task_id="train_evaluate_promote",
        python_callable=train,
        execution_timeout=timedelta(minutes=55),
    )
