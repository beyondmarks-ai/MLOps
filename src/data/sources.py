"""Operator-configured sources; uploads cannot choose network destinations or SQL."""

import io
import os
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from src.data import store

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def ingest_configured_source():
    store.initialize()
    imported = []
    if path := os.getenv("SOURCE_CSV"):
        if Path(path).stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("Source CSV exceeds 10 MiB")
        imported.append(store.add_dataset(pd.read_csv(path), "configured_csv"))
    if url := os.getenv("SOURCE_API_URL"):
        if not url.startswith("https://"):
            raise ValueError("Source API must use HTTPS")
        with requests.get(url, timeout=30, stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("Source API redirects are not allowed")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError("Source API response exceeds 10 MiB")
                chunks.append(chunk)
            imported.append(
                store.add_dataset(pd.read_json(io.BytesIO(b"".join(chunks))), "configured_api")
            )
    if database := os.getenv("SOURCE_DATABASE_URL"):
        source_engine = create_engine(database, future=True)
        try:
            with source_engine.connect() as conn:
                result = conn.execute(text(os.environ["SOURCE_SQL"]))
                rows = result.fetchmany(100001)
                if len(rows) > 100000:
                    raise ValueError("Database source exceeds 100,000 rows; import a smaller batch")
                df = pd.DataFrame(rows, columns=result.keys())
            imported.append(store.add_dataset(df, "configured_database"))
        finally:
            source_engine.dispose()
    return imported
