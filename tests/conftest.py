"""Shared pytest fixtures and configuration."""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on the Python path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolate_mlflow_runs():
    """Mocked MLflow logging tests must not leave implicit runs in later tests."""
    import mlflow

    while mlflow.active_run():
        mlflow.end_run()
    yield
    while mlflow.active_run():
        mlflow.end_run()
