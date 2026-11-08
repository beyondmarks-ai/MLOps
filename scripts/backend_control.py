"""Local Azure VM controls; uses the current Azure CLI login, never application keys."""

import json
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser

SUBSCRIPTION = "617db570-27f6-43a2-8d98-7b067bc2336b"
RESOURCE_GROUP = "rg-churn-mlops"
VM_NAME = "churn-mlops-vm"
APP_URL = "https://churn-mlops-617db570.centralindia.cloudapp.azure.com"


def azure(*arguments, timeout=90):
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI is missing. Install it, then run az login in PowerShell.")
    result = subprocess.run(
        [
            executable,
            "vm",
            *arguments,
            "--subscription",
            SUBSCRIPTION,
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            VM_NAME,
            "--only-show-errors",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError((result.stderr.strip() or "Azure command failed.")[:1500])
    return result.stdout


def power_state():
    data = json.loads(azure("get-instance-view", "--output", "json"))
    for status in data["instanceView"]["statuses"]:
        if status["code"].startswith("PowerState/"):
            return status["code"].split("/", 1)[1]
    raise RuntimeError("Azure did not return a VM power state. Try Refresh.")


def app_ready():
    try:
        with urllib.request.urlopen(APP_URL + "/health", timeout=5) as response:
            return response.status == 200 and json.load(response).get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def inspect_backend():
    state = power_state()
    if state == "running":
        return (
            "Ready — backend is online."
            if app_ready()
            else "VM running; application not ready yet."
        )
    if state == "deallocated":
        return "Stopped (deallocated) — compute billing stopped."
    if state == "stopped":
        return "Stopped but still allocated — click Stop to stop compute billing."
    return f"Azure state: {state}."


def change_power(action, report, timeout=900):
    if action not in ("start", "deallocate"):
        raise ValueError("Unsupported power action")
    azure(action, "--no-wait", "--output", "none")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = power_state()
        if action == "deallocate" and state == "deallocated":
            return "Stopped (deallocated) — compute billing stopped."
        if action == "start" and state == "running" and app_ready():
            return "Ready — backend is online. Click Open App."
        report(
            f"Azure: {state}. "
            + (
                "Waiting for the model and application; startup can take several minutes."
                if action == "start"
                else "Waiting for deallocation; please keep this window open."
            )
        )
        time.sleep(10)
    raise TimeoutError(
        "The wait timed out. Azure may still be working. Click Refresh before trying again."
    )


def main():
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title("Churn MLOps — Backend control")
    root.geometry("720x470")
    root.minsize(680, 470)
    style = ttk.Style(root)
    style.configure("TButton", padding=(12, 10), font=("Segoe UI", 11))
    style.configure("TLabel", font=("Segoe UI", 11))
    panel = ttk.Frame(root, padding=24)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Backend on demand", font=("Segoe UI", 20, "bold")).pack(anchor="w")
    ttk.Label(panel, text="Churn MLOps · Azure Central India").pack(anchor="w", pady=(4, 20))
    status = ScrolledText(panel, height=4, wrap="word", font=("Segoe UI", 11))
    status.pack(fill="x")

    def set_status(message):
        status.configure(state="normal")
        status.delete("1.0", "end")
        status.insert("1.0", message)
        status.configure(state="disabled")

    set_status("Checking Azure…")
    progress = ttk.Progressbar(panel, mode="indeterminate")
    progress.pack(fill="x", pady=(16, 16))
    row = ttk.Frame(panel)
    row.pack(anchor="w")
    events = queue.Queue()
    busy = False
    buttons = []

    def run(operation):
        nonlocal busy
        if busy:
            return
        busy = True
        for button in buttons:
            button.state(["disabled"])
        set_status("Contacting Azure…")
        progress.start()

        def worker():
            try:
                events.put(("done", operation()))
            except Exception as error:
                events.put(("done", f"Could not finish: {error}"))

        threading.Thread(target=worker, daemon=True).start()

    def stop():
        if messagebox.askyesno(
            "Stop backend?",
            "This takes the app offline and interrupts active training. Stored data stays.\n\n"
            "Deallocate the VM to stop compute charges?",
            parent=root,
        ):
            run(lambda: change_power("deallocate", lambda msg: events.put(("status", msg))))

    for title, command in (
        (
            "Start backend",
            lambda: run(lambda: change_power("start", lambda msg: events.put(("status", msg)))),
        ),
        ("Stop backend", stop),
        ("Refresh", lambda: run(inspect_backend)),
        ("Open App", lambda: webbrowser.open(APP_URL)),
    ):
        button = ttk.Button(row, text=title, command=command)
        button.pack(side="left", padx=(0, 8))
        buttons.append(button)
    help_text = ttk.Label(
        panel,
        text="Running: about $0.21/hour for compute. Disk, IP and storage charges remain when stopped.\n\n"
        "Uses your Azure CLI sign-in. If it has expired, run az login in PowerShell.\n"
        "Closing this launcher does not stop the backend. Use Stop when finished.",
        wraplength=640,
    )
    help_text.pack(anchor="w", pady=(20, 0))
    panel.bind("<Configure>", lambda event: help_text.configure(wraplength=event.width - 48))

    def poll():
        nonlocal busy
        while not events.empty():
            kind, message = events.get_nowait()
            set_status(message)
            if kind == "done":
                busy = False
                progress.stop()
                for button in buttons:
                    button.state(["!disabled"])
        root.after(150, poll)

    def close():
        if not busy or messagebox.askyesno(
            "Azure operation in progress",
            "The Azure operation continues if this window closes. Close anyway?",
            parent=root,
        ):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(150, poll)
    run(inspect_backend)
    root.mainloop()


if __name__ == "__main__":
    main()
