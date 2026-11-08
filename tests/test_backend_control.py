"""Power controls must wait for readiness and use deallocation to stop billing."""

from unittest.mock import Mock

import pytest

from scripts import backend_control as control


def test_start_waits_for_application_not_only_vm(monkeypatch):
    azure = Mock()
    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(
        control, "power_state", Mock(side_effect=["starting", "running", "running"])
    )
    ready = Mock(side_effect=[False, True])
    monkeypatch.setattr(control, "app_ready", ready)
    monkeypatch.setattr(control.time, "sleep", Mock())
    assert control.change_power("start", Mock()).startswith("Ready")
    azure.assert_called_once_with("start", "--no-wait", "--output", "none")
    assert ready.call_count == 2


def test_stop_waits_for_deallocation(monkeypatch):
    azure = Mock()
    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(control, "power_state", Mock(side_effect=["stopped", "deallocated"]))
    monkeypatch.setattr(control.time, "sleep", Mock())
    assert "billing stopped" in control.change_power("deallocate", Mock())
    azure.assert_called_once_with("deallocate", "--no-wait", "--output", "none")


def test_timeout_and_azure_failure_are_visible(monkeypatch):
    monkeypatch.setattr(control, "azure", Mock())
    with pytest.raises(TimeoutError, match="Refresh"):
        control.change_power("start", Mock(), timeout=0)
    monkeypatch.setattr(control, "azure", Mock(side_effect=RuntimeError("Login expired")))
    with pytest.raises(RuntimeError, match="Login expired"):
        control.change_power("deallocate", Mock())


def test_wrong_action_rejected_without_azure_call(monkeypatch):
    azure = Mock()
    monkeypatch.setattr(control, "azure", azure)
    with pytest.raises(ValueError):
        control.change_power("delete", Mock())
    azure.assert_not_called()


def test_azure_scope_and_command_errors(monkeypatch):
    monkeypatch.setattr(control.shutil, "which", lambda _: "az")
    run = Mock(return_value=Mock(returncode=0, stdout="ok"))
    monkeypatch.setattr(control.subprocess, "run", run)
    assert control.azure("start") == "ok"
    arguments = run.call_args.args[0]
    assert arguments[arguments.index("--subscription") + 1] == control.SUBSCRIPTION
    assert arguments[arguments.index("--name") + 1] == control.VM_NAME
    run.return_value = Mock(returncode=1, stderr="Login expired")
    with pytest.raises(RuntimeError, match="Login expired"):
        control.azure("start")
