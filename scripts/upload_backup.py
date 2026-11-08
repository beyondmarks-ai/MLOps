"""Upload a completed backup using the VM managed identity (no storage keys)."""

import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

if __name__ == "__main__":
    client = BlobServiceClient(
        f"https://{os.environ['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )
    for path in Path("/backup").glob("*.gz"):
        with path.open("rb") as stream:
            client.get_blob_client("backups", path.name).upload_blob(stream, overwrite=False)
        print(f"Uploaded {path.name}")
