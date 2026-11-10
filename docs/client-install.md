# Install on a client's Windows PC

This installs a separate local copy: dashboard, prediction API, MySQL, MLflow,
Airflow, automatic training and monitoring. It generates new credentials for the
client. No Azure subscription, Azure credit, Python installation or GitHub login
is needed. Initial predictions use the public fictional telecom benchmark;
they do not establish accuracy for the client's customers.

## Requirements

- Supported x64 Windows 11 (23H2 or newer), hardware virtualization enabled.
- WSL 2.1.5 or newer; setup requests installation/update when necessary.
- At least 8 GB RAM; **16 GB recommended**, with approximately 8 GB available to
  Docker during training. At least 30 GB free for images and data; allow more as
  datasets/models accumulate. Docker normally stores data on the Windows system drive.
- Internet during installation for Git, Docker images, Python dependencies and
  the checksum-verified public benchmark. Local prediction works offline afterward.
- Permission to approve Windows administrator prompts. Run setup as the client's
  own Windows account; approve individual software installations when prompted.
- Microsoft App Installer (`winget`). Install/update it from Microsoft Store if
  setup reports it missing. Docker Desktop's license terms apply; some businesses
  need a paid Docker subscription: https://docs.docker.com/subscription/desktop-license/

## Client installation

Open **Windows PowerShell** and paste:

```powershell
$installer = Join-Path $env:TEMP 'install-mlops-client.ps1'
Invoke-WebRequest 'https://raw.githubusercontent.com/beyondmarks-ai/MLOps/main/scripts/install-client.ps1' -OutFile $installer -UseBasicParsing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
```

The script downloads executable project code. You can inspect the downloaded file
before the last command. Execution policy is bypassed only for that process.

1. Approve Git/Docker/WSL administrator prompts. Setup requests WSL installation
   if missing. If asked to restart, restart Windows and paste the same commands again.
2. Complete Docker Desktop's first-launch terms and select the WSL 2/Linux container
   backend. Hardware virtualization might need enabling in the PC's BIOS/UEFI.
3. Allow approximately 20-45 minutes for downloads, builds and initial model training;
   slower PCs/connections can take longer. The installer opens the dashboard only
   after an authenticated prediction succeeds.
4. Open **Desktop > MLOps Local > Credentials**, copy the administrator key, and
   paste it into the dashboard. Airflow's username and generated password are in
   the same private file. Docker Desktop does not require a personal account for
   ordinary local use, although an employer's policy may require sign-in.

The repository is installed in `%LOCALAPPDATA%\MLOps`. To choose another private
directory, add `-InstallDirectory 'D:\MLOps'` to the final command. Keep the folder
out of shared/synchronized locations. If setup is interrupted, rerun the same
command/directory or use the **Install** desktop shortcut. Existing checkouts,
passwords, model history and data are preserved. Setup does not automatically
update an existing checkout.

## Everyday use

In **Desktop > MLOps Local**:

| Shortcut | Action |
|---|---|
| Start | Starts Docker and the backend, checks the model/API, opens the dashboard |
| Stop | Stops this project's containers; retains data and models |
| Open | Opens the dashboard if the backend is running |
| Credentials | Opens the client's private credentials file |
| Status | Shows container status and health |
| Install | Resumes installation, including unfinished initial training |

`Client-Control.cmd` in the installed folder provides the same actions as a menu.
The existing `Backend-Control.cmd` controls the original owner's Azure VM and is
**not** the local launcher.

Closing a browser/terminal does not stop the backend. Use **Stop** when finished.
Containers left running can restart when Docker starts. Stop leaves Docker Desktop
itself running so other projects are unaffected; you may quit Docker Desktop after
stopping this project if no other workloads need it. There are no Azure charges
for this local installation.

Default addresses (setup chooses nearby free ports if needed):

- Dashboard/API: `http://127.0.0.1:8088`
- Airflow: `http://127.0.0.1:8188`
- MLflow: `http://127.0.0.1:5001`

Use the exact addresses in Credentials. All published ports bind to loopback;
other computers cannot connect. MLflow has no separate login on this local
profile. Other applications/users on the same PC can reach loopback services,
so use a trusted PC with a protected Windows account.

## Credentials, data and ownership

`.client\.env` contains independent API/admin keys, database passwords, Airflow's
administrator password, web secret and Fernet encryption key. `.client\CREDENTIALS.txt`
provides login instructions. Windows permissions restrict this directory to the
installing user, Windows administrators and SYSTEM; both Git and Docker build
contexts exclude it. These files are private plaintext, not a password vault.
Never email/commit them or put them in an ordinary shared folder.

The client owns this local installation and its generated credentials. This does
not transfer ownership of the source GitHub repository or the original Azure
subscription. No original owner's credentials are copied.

Database/model data live in Docker volumes prefixed `mlops-client_`. Keep a secure
backup of **both** the entire `.client` directory and all these volumes. Stop the
backend before taking a Docker volume backup/export. Do not use Docker's factory
reset, delete volumes, or run `docker compose down -v` unless deliberately erasing
the installation. Restoring credentials alone does not restore data. This local
installer does not configure scheduled/off-PC backups.

## Troubleshooting and real customer data

- **Docker not ready:** finish Docker Desktop setup, use Linux containers, update
  WSL (`wsl --update` in an administrator terminal), then rerun. If virtualization
  is disabled, enable it in BIOS/UEFI. The script cannot change BIOS settings.
- **Build/training fails:** check disk/RAM/network, use Status, then Install to
  resume. Credentials and volumes are not regenerated. Download checksum mismatch
  intentionally stops installation until the changed dataset is reviewed.
- **Port already in use after setup:** close the conflicting application or change
  the corresponding port in `.client\.env`, then run Start to recreate the port
  mapping and refresh shortcuts/credential instructions.
- **Credentials missing but data exists:** restore the original `.client` backup.
  Setup refuses to generate new database passwords against existing volumes.
- **Before real customer deployment:** validate the model with representative
  labeled customer data. The initial database contains demo customers: do not
  treat mixed demo/customer training as customer validation. Arrange a separate
  clean data/model environment, backup policy and measured validation before
  relying on predictions for business decisions.

The automated tests cover Windows script helpers and a fresh Linux-container
stack. They cannot certify every client's BIOS, Windows policies, first-run Docker
dialogs or hardware; those still require a trial on the destination PC.
