"""Choose a demonstration threshold on validation data, never the holdout."""

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import precision_recall_curve


def select_threshold(labels, probabilities):
    labels, probabilities = np.asarray(labels), np.asarray(probabilities)
    if (
        labels.ndim != 1
        or probabilities.shape != labels.shape
        or set(np.unique(labels)) != {0, 1}
        or not np.isfinite(probabilities).all()
        or ((probabilities < 0) | (probabilities > 1)).any()
    ):
        raise ValueError("Threshold selection needs both binary classes and finite probabilities")
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    f1 = np.divide(
        2 * precision[:-1] * recall[:-1],
        precision[:-1] + recall[:-1],
        out=np.zeros_like(thresholds),
        where=(precision[:-1] + recall[:-1]) > 0,
    )
    best = np.flatnonzero(np.isclose(f1, f1.max(), rtol=0, atol=1e-12))
    return float(thresholds[best[np.argmin(abs(thresholds[best] - 0.5))]])


class ThresholdClassifier(ClassifierMixin, BaseEstimator):
    """Keep the fitted estimator and its decision threshold in the same artifact."""

    def __init__(self, estimator, threshold=0.5):
        self.estimator = estimator
        self.threshold = threshold

    @property
    def classes_(self):
        return self.estimator.classes_

    def fit(self, X, y):
        self.estimator.fit(X, y)
        return self

    def predict_proba(self, X):
        return self.estimator.predict_proba(X)

    def predict(self, X):
        return self.classes_[(self.predict_proba(X)[:, 1] >= self.threshold).astype(int)]
