"""Create the local administrator and train the first demo without replacing client data."""

import os


def ensure_admin(security_manager, password):
    if security_manager.find_user(username="admin"):
        return
    user = security_manager.add_user(
        username="admin",
        first_name="Local",
        last_name="Administrator",
        email="admin@localhost",
        role=security_manager.find_role("Admin"),
        password=password,
    )
    if not user:
        raise RuntimeError("Could not create the Airflow administrator")


def ensure_demo(store, download, run_cycle):
    store.initialize()
    if not store.overview()["datasets"]:
        frame, _ = download()
        store.add_dataset(frame, "public_maven_telecom_benchmark")
    # Pending work survives interrupted installs; completed training is not repeated.
    return run_cycle()


def main():
    from airflow.www.app import cached_app

    from scripts.prepare_benchmark import download
    from src.data import store
    from src.training.lifecycle import run_cycle

    app = cached_app()
    with app.app_context():
        ensure_admin(app.appbuilder.sm, os.environ["CLIENT_ADMIN_PASSWORD"])
    result = ensure_demo(store, download, run_cycle)
    print(f"Local bootstrap: {result['decision']}")


if __name__ == "__main__":
    main()
