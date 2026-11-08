"""Deployment restores cost-saving power state even when guest commands fail."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import github_deploy as deployment

COMMIT = "a" * 40


@pytest.fixture
def setup_deployment(monkeypatch):
    monkeypatch.setattr(deployment, "power_state", lambda: "deallocated")
    power = Mock(return_value="Deallocated")
    monkeypatch.setattr(deployment, "change_power", power)
    monkeypatch.setattr(deployment, "app_ready", lambda: True)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    def command(*args, **kwargs):
        if args[0] == "run-command":
            script = Path(args[args.index("--scripts") + 1][1:]).read_text()
            assert COMMIT in script and "__COMMIT__" not in script
            assert "api api2" in script
            return json.dumps({"value": [{"message": f"CHURN_DEPLOYED_{COMMIT}"}]})
        return ""

    azure = Mock(side_effect=command)
    monkeypatch.setattr(deployment, "azure", azure)
    return azure, power


def test_stopped_vm_starts_deploys_and_deallocates(setup_deployment):
    azure, power = setup_deployment
    assert "deallocated" in deployment.deploy(COMMIT)
    assert azure.call_args_list[0].args[0] == "start"
    power.assert_called_once_with("deallocate", print)


def test_running_vm_is_left_running(setup_deployment, monkeypatch):
    azure, power = setup_deployment
    monkeypatch.setattr(deployment, "power_state", lambda: "running")
    assert "left running" in deployment.deploy(COMMIT)
    assert azure.call_args_list[0].args[0] == "run-command"
    power.assert_not_called()


def test_guest_failure_restores_power_even_if_azure_cli_succeeds(setup_deployment):
    azure, power = setup_deployment
    azure.side_effect = None
    azure.return_value = '{"value": [{"message": "build failed"}]}'
    with pytest.raises(RuntimeError, match="completion check"):
        deployment.deploy(COMMIT)
    power.assert_called_once_with("deallocate", print)


def test_failed_public_health_restores_power(setup_deployment, monkeypatch):
    _, power = setup_deployment
    monkeypatch.setattr(deployment, "app_ready", lambda: False)
    with pytest.raises(RuntimeError, match="HTTPS"):
        deployment.deploy(COMMIT)
    power.assert_called_once_with("deallocate", print)


def test_invalid_commit_and_transitional_vm_are_not_mutated(setup_deployment, monkeypatch):
    azure, power = setup_deployment
    with pytest.raises(ValueError):
        deployment.deploy("main; echo unsafe")
    monkeypatch.setattr(deployment, "power_state", lambda: "deallocating")
    with pytest.raises(RuntimeError, match="current operation"):
        deployment.deploy(COMMIT)
    azure.assert_not_called()
    power.assert_not_called()
