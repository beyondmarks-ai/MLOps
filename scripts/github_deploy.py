"""Deploy one GitHub commit using OIDC and restore the VM's initial power state."""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from scripts.backend_control import app_ready, azure, change_power, power_state


def deploy(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Deployment requires a full lowercase Git commit SHA")
    initial = power_state()
    if initial not in ("running", "stopped", "deallocated"):
        raise RuntimeError(f"VM is {initial}; wait for its current operation to finish")
    try:
        if initial != "running":
            print("Starting the VM for deployment.", flush=True)
            azure("start", "--output", "none", timeout=600)
        script = Path("deploy/github-release.sh").read_text().replace("__COMMIT__", commit)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deploy.sh"
            path.write_bytes(script.encode())
            result = json.loads(
                azure(
                    "run-command",
                    "invoke",
                    "--command-id",
                    "RunShellScript",
                    "--scripts",
                    "@" + str(path),
                    "--output",
                    "json",
                    timeout=1800,
                )
            )
        # Run Command can return CLI success even when the guest script failed.
        messages = "\n".join(item.get("message", "") for item in result.get("value", []))
        if f"CHURN_DEPLOYED_{commit}" not in messages:
            raise RuntimeError(
                "VM deployment failed its completion check. Inspect Azure Run Command output."
            )
        if not app_ready():
            raise RuntimeError("VM checks passed but the public HTTPS application is not healthy")
        print(f"Verified deployment of {commit} through public HTTPS.", flush=True)
    finally:
        if initial != "running":
            print(change_power("deallocate", print), flush=True)
    summary = f"Deployed `{commit}`. HTTPS health passed. VM {'left running' if initial == 'running' else 'deallocated to stop compute billing'}.\n"
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write(summary)
    return summary


if __name__ == "__main__":
    print(deploy(sys.argv[1]))
