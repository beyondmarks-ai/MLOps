# Use the Azure application from a client PC

The application runs on the project owner's Azure VM. The client only needs an
internet connection and a current browser such as Edge or Chrome. No Git clone,
installer, Docker, WSL, Python, or Azure login is required on the client PC.
The local installer's RAM requirement does not apply to this browser setup.

## Client: open the app

1. Ask the project owner to start the backend before the demonstration.
2. Open **https://churn-mlops-617db570.centralindia.cloudapp.azure.com**.
3. Get the application administrator key privately from the owner.
4. Paste it into **Access key**, then click **Refresh status**.
5. In **3. Predict customer churn**, enter customer details and click **Get prediction**.

Bookmark the application address for next time. The key stays in the page's memory,
so you may need to enter it again after reopening or reloading the page. Never put
keys in a bookmark URL, screenshot, public repository, or support message.

The dashboard shows model status, candidate comparison and recent training/monitoring
activity. Predictions show the churn probability and decision. The existing model
uses a public fictional telecom benchmark; no dataset upload is needed to try it.
Its predictions are a demonstration, not verified accuracy for the client's customers.

## Owner: start and stop the backend

On the owner's configured computer, double-click **Backend-Control.cmd** and click
**Start backend**. Wait until it reports the app ready, then give the client the URL.
The launcher needs this project's Python environment and the owner's Azure CLI login.

Alternatively, use Azure CLI on the owner's computer:

```powershell
az vm start --subscription 617db570-27f6-43a2-8d98-7b067bc2336b --resource-group rg-churn-mlops --name churn-mlops-vm
```

After the demonstration and any active work finishes, use **Stop backend**, or:

```powershell
az vm deallocate --subscription 617db570-27f6-43a2-8d98-7b067bc2336b --resource-group rg-churn-mlops --name churn-mlops-vm
```

Stopping takes the app offline for everyone. Closing the browser does not stop
Azure billing. Deallocation stops VM compute charges; disk, IP and storage charges
continue. Data/models persist, but training, monitoring and scheduled backups do
not run while the VM is off. There is no automatic inactivity shutdown.

## Access and troubleshooting

- **Site cannot be reached:** the owner should check VM state and app readiness.
  A stopped VM cannot serve the dashboard; allow several minutes after starting it.
- **Access denied:** check that the full administrator key was pasted, without
  extra spaces. The prediction-only key cannot access administrator controls.
- **Model not ready:** let startup finish. If the problem persists, the owner
  should inspect the services using the Azure operations guide.
- **Airflow or MLflow demonstration:** these service interfaces remain private.
  The browser dashboard shows the main results; an authorized owner can use the
  documented SSH tunnel for Airflow. They are not exposed publicly for this switch.

The client needs only application access. Keep Azure sign-in, SSH keys, database
passwords and VM controls with the owner. Shared administrator keys grant access to
the same hosted data and training controls; share only with the intended client.
Self-service VM Start/Stop would require a separate, limited Azure access setup.

See [Azure operations](azure-operations.md) for maintenance, backups and recovery.
