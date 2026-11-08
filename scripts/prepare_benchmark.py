"""Reproducibly map Maven's fictional telecom benchmark into the churn schema."""

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.validation import validate_schema

SOURCE_URL = (
    "https://maven-datasets.s3.amazonaws.com/Telecom+Customer+Churn/Telecom+Customer+Churn.zip"
)
SOURCE_SHA256 = "c4c64db132d7423abb0a522d60120bbd1d17b3d483eccaaa447561a5e617efba"


def prepare(frame):
    if not frame["Customer Status"].isin(["Stayed", "Churned", "Joined"]).all():
        raise ValueError("Unknown customer status in benchmark")
    data = frame.loc[frame["Customer Status"] != "Joined"].copy()

    def flag(column):
        values = data[column].fillna("No").map({"Yes": 1, "No": 0})
        if values.isna().any():
            raise ValueError(f"Unknown benchmark value in {column}")
        return values.astype(int)

    result = pd.DataFrame(index=data.index)
    for source, target in {
        "Age": "age",
        "Tenure in Months": "tenure_months",
        "Monthly Charge": "monthly_charges",
        "Total Charges": "total_charges",
    }.items():
        result[target] = pd.to_numeric(data[source], errors="raise")
    negative_charges = int((result.monthly_charges < 0).sum())
    result.loc[result.monthly_charges < 0, "monthly_charges"] = np.nan
    for source, target in {
        "Premium Tech Support": "has_tech_support",
        "Online Security": "has_online_security",
        "Online Backup": "has_backup",
        "Device Protection Plan": "has_device_protection",
        "Married": "has_partner",
    }.items():
        result[target] = flag(source)
    result["is_senior_citizen"] = (result.age >= 65).astype(int)
    result["has_dependents"] = (data["Number of Dependents"] > 0).astype(int)
    # Count paid subscriptions/add-ons; streaming usage is not an extra product in this source.
    result["num_products"] = sum(
        flag(column)
        for column in [
            "Phone Service",
            "Internet Service",
            "Online Security",
            "Online Backup",
            "Device Protection Plan",
            "Premium Tech Support",
            "Unlimited Data",
        ]
    )
    result["contract_type"] = data["Contract"].map(
        {"Month-to-Month": "Month-to-month", "One Year": "One year", "Two Year": "Two year"}
    )
    result["payment_method"] = data["Payment Method"].replace({"Mailed Check": "Mailed check"})
    result["internet_service"] = (
        data["Internet Type"].fillna("No").replace({"Fiber Optic": "Fiber optic"})
    )
    result["churn"] = (data["Customer Status"] == "Churned").astype(int)
    validation = validate_schema(result)
    if not validation.passed:
        raise ValueError(validation.summary())
    manifest = {
        "source_url": SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "source_rows": len(frame),
        "training_rows": len(result),
        "joined_rows_excluded": len(frame) - len(result),
        "negative_charges_set_missing": negative_charges,
        "label_counts": result.churn.value_counts().to_dict(),
        "dataset_kind": "public_benchmark_fictional_customers",
        "license": "Public Domain (Maven source page)",
        "source_page": "https://mavenanalytics.io/data-playground/telecom-customer-churn",
    }
    return result, manifest


def download():
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        archive = response.read(25 * 1024 * 1024 + 1)
    if hashlib.sha256(archive).hexdigest() != SOURCE_SHA256:
        raise ValueError("Benchmark checksum changed; review the source before accepting new data")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        info = zipped.getinfo("telecom_customer_churn.csv")
        if info.file_size > 20 * 1024 * 1024:
            raise ValueError("Benchmark CSV exceeds its size limit")
        with zipped.open(info) as source:
            return prepare(pd.read_csv(source))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/benchmarks/maven.csv")
    args = parser.parse_args()
    frame, manifest = download()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))
