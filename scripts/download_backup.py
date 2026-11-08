"""Download the latest MySQL backup for an isolated restore check."""

import gzip
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

if __name__ == "__main__":
    client = BlobServiceClient(
        f"https://{os.environ['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    ).get_container_client("backups")
    latest = max(client.list_blobs(name_starts_with="mysql-"), key=lambda blob: blob.last_modified)
    data = client.download_blob(latest.name).readall()
    Path("/restore/mysql.sql").write_bytes(gzip.decompress(data))
    print(f"Downloaded backup {latest.name} for isolated restore")
