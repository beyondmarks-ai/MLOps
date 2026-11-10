from unittest.mock import Mock

import pytest

from scripts.bootstrap_client import ensure_admin, ensure_demo


def test_existing_admin_password_is_never_replaced():
    security = Mock()
    security.find_user.return_value = object()
    ensure_admin(security, "fresh-password")
    security.add_user.assert_not_called()


def test_admin_creation_failure_is_reported():
    security = Mock()
    security.find_user.return_value = None
    security.add_user.return_value = None
    with pytest.raises(RuntimeError, match="administrator"):
        ensure_admin(security, "fresh-password")
    assert security.add_user.call_args.kwargs["password"] == "fresh-password"


def test_empty_install_seeds_once_and_resumes_pending_training():
    store, download, train = Mock(), Mock(), Mock()
    store.overview.side_effect = [{"datasets": []}, {"datasets": ["existing"]}]
    download.return_value = ("frame", {})
    ensure_demo(store, download, train)
    ensure_demo(store, download, train)
    download.assert_called_once()
    store.add_dataset.assert_called_once_with("frame", "public_maven_telecom_benchmark")
    assert train.call_count == 2


def test_client_data_is_not_mixed_with_demo():
    store, download, train = Mock(), Mock(), Mock()
    store.overview.return_value = {"datasets": ["client-data"]}
    ensure_demo(store, download, train)
    download.assert_not_called()
    store.add_dataset.assert_not_called()
