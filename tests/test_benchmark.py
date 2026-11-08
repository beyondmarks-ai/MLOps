"""Public benchmark mapping and artifact threshold behavior."""

import pickle

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from scripts.prepare_benchmark import prepare
from src.training.threshold import ThresholdClassifier, select_threshold


def test_threshold_improves_validation_f1_without_changing_scores():
    labels = np.array([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.3, 0.4])
    threshold = select_threshold(labels, probabilities)
    assert threshold == 0.3
    assert f1_score(labels, probabilities >= threshold) == 1
    assert f1_score(labels, probabilities >= 0.5) == 0
    model = ThresholdClassifier(LogisticRegression(), threshold).fit(
        np.array([[0], [1], [2], [3]]), labels
    )
    restored = pickle.loads(pickle.dumps(model))
    np.testing.assert_array_equal(model.predict([[1], [2]]), restored.predict([[1], [2]]))
    np.testing.assert_array_equal(model.predict_proba([[1]]), model.estimator.predict_proba([[1]]))


@pytest.mark.parametrize(
    "labels,scores", [([0, 0], [0.1, 0.2]), ([0, 1], [0.1, np.nan]), ([0, 1], [0.1, 2])]
)
def test_threshold_rejects_invalid_validation_data(labels, scores):
    with pytest.raises(ValueError):
        select_threshold(labels, scores)


def test_benchmark_mapping_excludes_leakage_and_records_cleaning():
    sample = {
        "Customer Status": "Stayed",
        "Age": 70,
        "Tenure in Months": 24,
        "Monthly Charge": 60.0,
        "Total Charges": 1440.0,
        "Number of Dependents": 2,
        "Contract": "One Year",
        "Payment Method": "Bank Withdrawal",
        "Internet Type": "Cable",
        "Phone Service": "Yes",
        "Internet Service": "Yes",
        "Married": "Yes",
        "Online Security": "No",
        "Online Backup": "No",
        "Premium Tech Support": "No",
        "Device Protection Plan": "No",
        "Unlimited Data": "No",
        "Churn Reason": "Leaking label",
        "Customer ID": "excluded",
    }
    source = pd.DataFrame([sample] * 40)
    source.loc[0, "Monthly Charge"] = -10
    source.loc[1, "Customer Status"] = "Joined"
    source.loc[2, "Customer Status"] = "Churned"
    frame, manifest = prepare(source)
    assert len(frame) == 39 and frame.churn.sum() == 1
    assert manifest["joined_rows_excluded"] == 1
    assert manifest["negative_charges_set_missing"] == 1
    assert pd.isna(frame.loc[0, "monthly_charges"])
    assert frame.num_products.eq(2).all()
    assert frame.has_dependents.eq(1).all() and frame.is_senior_citizen.eq(1).all()
    assert "Churn Reason" not in frame and "Customer ID" not in frame
    source["Churn Reason"] = "Changed leakage"
    pd.testing.assert_frame_equal(frame, prepare(source)[0])
    source.loc[0, "Customer Status"] = "Unknown"
    with pytest.raises(ValueError, match="Unknown customer status"):
        prepare(source)
