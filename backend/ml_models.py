# backend/ml_models.py
"""
Candidate classifiers for the EXPERIMENTAL "Red" risk probability (advisory only - the
rule-based engine in anomaly_engine.py is what creates alerts).

Shared by analytics_engine.py (the model the API serves) and scripts/evaluate_models.py
(the comparison), so the evaluated model and the served model can never drift apart.

Hyper-parameters are fixed in advance (not tuned on the evaluation folds):
  * xgboost_original - the configuration used before (kept for comparison). With only ~3
    positive examples per training fold, XGBoost's default min_child_weight=1 blocks almost
    every split, so the probabilities never leave the base rate and "Red" is never predicted.
  * xgboost_small_data - same learner configured for tiny data: min_child_weight lowered so
    splits are possible, scale_pos_weight balances the 4:11 classes.
  * logistic_regression - standardised features, class-balanced, L2 (the simplest model).
  * random_forest - class-balanced bagged trees.
The winner is chosen by a rule declared here (SELECTION_RULE), never by accuracy alone.
"""
from typing import Any, Callable

SELECTION_RULE = ("Highest F1 for the Red (positive) class; ties broken by ROC-AUC, then balanced "
                  "accuracy, then the simpler model (order of CANDIDATES).")


def _xgb(**params):
    import xgboost as xgb
    return xgb.XGBClassifier(random_state=42, eval_metric="logloss", **params)


def _logreg():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", C=1.0, max_iter=1000))


def _forest():
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_estimators=300, class_weight="balanced", min_samples_leaf=1, random_state=42)


# name -> (label, factory, kind); kind picks the SHAP explainer. Order = simplicity for tie-breaks.
CANDIDATES: dict[str, tuple[str, Callable[[], Any], str]] = {
    "logistic_regression": ("Logistic Regression (standardised, class-balanced)", _logreg, "linear"),
    "random_forest": ("Random Forest (300 trees, class-balanced)", _forest, "tree"),
    "xgboost_small_data": ("XGBoost (min_child_weight=0.1, scale_pos_weight=neg/pos)", None, "tree"),
    "xgboost_original": ("XGBoost (original: 50 trees, depth 2, lr 0.1, defaults)", None, "tree"),
}


def make_model(name: str, n_pos: int = 1, n_neg: int = 1):
    """Fresh, unfitted estimator. XGBoost variants need the class counts of the TRAINING data only."""
    if name == "xgboost_original":
        return _xgb(n_estimators=50, max_depth=2, learning_rate=0.1)
    if name == "xgboost_small_data":
        return _xgb(n_estimators=100, max_depth=2, learning_rate=0.1, min_child_weight=0.1,
                    scale_pos_weight=(n_neg / n_pos) if n_pos else 1.0)
    return CANDIDATES[name][1]()


def loocv_evaluate(name: str, X, y) -> dict:
    """Leave-one-out CV: every record is predicted once by a model trained on the others.
    Returns out-of-fold predictions/probabilities and the standard metrics."""
    import numpy as np
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)
    from sklearn.model_selection import LeaveOneOut

    y_pred, y_prob = np.zeros(len(y), dtype=int), np.zeros(len(y))
    for train_idx, test_idx in LeaveOneOut().split(X):
        ytr = y[train_idx]
        model = make_model(name, int(ytr.sum()), int(len(ytr) - ytr.sum())).fit(X[train_idx], ytr)
        y_prob[test_idx] = model.predict_proba(X[test_idx])[:, 1]
        y_pred[test_idx] = model.predict(X[test_idx])
    return {
        "y_pred": y_pred.tolist(),
        "y_prob": [round(float(p), 4) for p in y_prob],
        "accuracy": float(accuracy_score(y, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, y_pred)),
        "precision_red": float(precision_score(y, y_pred, zero_division=0)),
        "recall_red": float(recall_score(y, y_pred, zero_division=0)),
        "f1_red": float(f1_score(y, y_pred, zero_division=0)),
        "f1_macro": float(f1_score(y, y_pred, average="macro", zero_division=0)),
        "roc_auc": float(roc_auc_score(y, y_prob)),
        "confusion_matrix": confusion_matrix(y, y_pred, labels=[0, 1]).tolist(),
    }


def select_best(results: dict[str, dict]) -> str:
    """Applies SELECTION_RULE to {name: loocv_evaluate(...)} (dict order = simplicity)."""
    order = list(CANDIDATES)
    return max(results, key=lambda n: (round(results[n]["f1_red"], 6), round(results[n]["roc_auc"], 6),
                                       round(results[n]["balanced_accuracy"], 6), -order.index(n)))


def label(name: str) -> str:
    return CANDIDATES[name][0]


def kind(name: str) -> str:
    return CANDIDATES[name][2]
