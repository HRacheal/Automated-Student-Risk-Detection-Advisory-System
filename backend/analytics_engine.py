# backend/analytics_engine.py
"""
EXPERIMENTAL ML predictive risk (best of the candidate classifiers in ml_models.py + SHAP).

The model is chosen by leave-one-out comparison of Logistic Regression, Random Forest and two
XGBoost configurations (see ml_models.SELECTION_RULE). It replaced a fixed XGBoost that, with
default min_child_weight on ~3 positive examples per fold, could not split and never predicted Red.

This is deliberately separate from the rule-based anomaly engine:
  * Rule-based anomalies  = facts detected in the source data (explainable, auditable).
  * ML predictive risk    = a probability learned from historical labels. It is
                            advisory only and never creates alerts.

Training data: the legacy `students` + `lms_activity` tables (advisor-assigned
Red/Yellow/Green labels). That dataset is very small, so the model is validated
with leave-one-out cross-validation and the real metric + sample size are
reported alongside every prediction. No performance figure is invented.

xgboost / shap / scikit-learn are optional: if they are not installed the
application keeps working and predictions report "unavailable".
"""
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from domain import StudentRecord

# Features that can be computed from RosarioSIS/Moodle data AND exist in the training set.
FEATURES = ["completed_units", "cumulative_gpa", "tuition_balance", "missed_assignments_count"]
FEATURE_LABELS = {
    "completed_units": "Completed units",
    "cumulative_gpa": "Cumulative GPA",
    "tuition_balance": "Tuition balance",
    "missed_assignments_count": "Missed assignments",
}
DISCLAIMER = ("Experimental model trained on a small historical dataset. Use as a supplementary "
              "signal only; it does not prove risk and does not create alerts.")

_lock = threading.RLock()
_state: dict[str, Any] = {"model": None, "explainer": None, "metrics": None, "error": None, "kind": None}


def load_training_data(db: Session):
    import pandas as pd
    from models import LMSActivity, Student

    rows = (
        db.query(Student.student_id, Student.completed_units, Student.cumulative_gpa, Student.tuition_balance,
                 LMSActivity.missed_assignments_count, LMSActivity.risk_level)
        .join(LMSActivity, LMSActivity.student_id == Student.student_id)
        .all()
    )
    df = pd.DataFrame(rows, columns=["student_id"] + FEATURES + ["risk_level"])
    df = df.dropna(subset=["risk_level"])
    for col in FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["target"] = (df["risk_level"].str.strip().str.lower() == "red").astype(int)
    return df


def train_risk_classifier(db: Session) -> dict:
    """Compare the candidate classifiers (ml_models.py) with leave-one-out CV on the legacy labelled
    dataset, pick one with the pre-declared SELECTION_RULE, then fit it on all records."""
    import ml_models

    with _lock:
        try:
            import numpy as np  # noqa: F401
            import sklearn  # noqa: F401
            import xgboost  # noqa: F401
        except ImportError as exc:
            _state.update(model=None, explainer=None, metrics=None, kind=None,
                          error=f"ML libraries not installed ({exc.name}).")
            return status()

        df = load_training_data(db)
        n = len(df)
        positives = int(df["target"].sum())
        if n < 6 or positives < 2 or positives > n - 2:
            _state.update(model=None, explainer=None, metrics=None, kind=None,
                          error=f"Not enough labelled data to train (n={n}, high-risk={positives}).")
            return status()

        X = df[FEATURES].to_numpy(dtype=float)
        y = df["target"].to_numpy()
        results = {name: ml_models.loocv_evaluate(name, X, y) for name in ml_models.CANDIDATES}
        best = ml_models.select_best(results)
        r = results[best]

        model = ml_models.make_model(best, positives, n - positives).fit(X, y)
        kind = ml_models.kind(best)
        explainer = None
        shap_note = None
        if kind == "tree":
            try:
                import shap
                explainer = shap.TreeExplainer(model)
            except Exception as exc:  # shap missing or incompatible
                shap_note = f"SHAP explanations unavailable ({exc.__class__.__name__})."
        else:
            shap_note = "linear model: exact per-feature contributions (coefficient x standardised value)"

        metrics = {
            "algorithm": f"{ml_models.label(best)} (target: legacy 'Red' label)",
            "model_key": best,
            "training_samples": n,
            "high_risk_samples": positives,
            "validation": "leave-one-out cross-validation",
            "loocv_accuracy": round(r["accuracy"], 3),
            "loocv_precision_high_risk": round(r["precision_red"], 3),
            "loocv_recall_high_risk": round(r["recall_red"], 3),
            "loocv_f1_high_risk": round(r["f1_red"], 3),
            "loocv_roc_auc": round(r["roc_auc"], 3),
            "selection_rule": ml_models.SELECTION_RULE,
            "candidates": {name: {k: round(v[k], 3) for k in ("accuracy", "f1_red", "roc_auc")}
                           for name, v in results.items()},
            "features": FEATURES,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warning": f"Only {n} labelled records ({positives} Red) and the model was chosen from "
                       f"{len(results)} candidates on the same records - metrics are optimistic, have very "
                       f"high variance and are not evidence of real-world accuracy.",
            "shap": "enabled" if explainer else shap_note,
        }
        _state.update(model=model, explainer=explainer, metrics=metrics, error=None, kind=kind)
        return status()


# Backwards-compatible name (POST /api/ml/train and older imports)
train_xgboost_and_shap = train_risk_classifier


def _contributions(model, x) -> Optional[list[float]]:
    """Per-feature contribution to the Red prediction (SHAP for trees, exact for the linear model)."""
    import numpy as np

    if _state.get("kind") == "linear":
        scaler, lr = model.steps[0][1], model.steps[-1][1]
        return [float(v) for v in lr.coef_[0] * scaler.transform(x)[0]]
    if _state["explainer"] is None:
        return None
    values = _state["explainer"].shap_values(x)
    if isinstance(values, list):          # older shap: [class0, class1]
        values = values[1]
    values = np.asarray(values)
    if values.ndim == 3:                  # (samples, features, classes)
        values = values[:, :, 1]
    return [float(v) for v in values[0]]


def ensure_model(db: Session) -> None:
    """Train once per process (thread-safe); later calls return immediately."""
    with _lock:
        if _state["model"] is not None or _state["error"] is not None:
            return
        try:
            train_risk_classifier(db)
        except Exception as exc:
            db.rollback()
            _state["error"] = f"Training failed: {exc.__class__.__name__}: {exc}"


def status() -> dict:
    return {"trained": _state["model"] is not None, "metrics": _state["metrics"],
            "error": _state["error"], "disclaimer": DISCLAIMER}


def _features_for(rec: StudentRecord) -> tuple[Optional[list[float]], list[str]]:
    values = {
        "completed_units": rec.completed_units,
        "cumulative_gpa": rec.cumulative_gpa,
        "tuition_balance": rec.financial.balance if rec.financial.available else None,
        "missed_assignments_count": (len(rec.lms.missed_assignments)
                                     if rec.lms.available and rec.lms.capabilities.get("assignments") else None),
    }
    missing = [FEATURE_LABELS[k] for k, v in values.items() if v is None]
    if missing:
        return None, missing
    return [float(values[k]) for k in FEATURES], []


def predict_for_record(rec: StudentRecord) -> Optional[dict]:
    """Returns an ML prediction dict (never raises). None-valued fields are explained."""
    try:
        model = _state["model"]
        if model is None:
            return {"status": "unavailable", "reason": _state["error"] or "Model not trained.",
                    "disclaimer": DISCLAIMER}
        x, missing = _features_for(rec)
        if x is None:
            return {"status": "insufficient_data",
                    "reason": "Required inputs unavailable from source systems: " + ", ".join(missing),
                    "disclaimer": DISCLAIMER}
        import numpy as np
        arr = np.array([x])
        prob = float(model.predict_proba(arr)[0][1])
        factors = []
        contributions = _contributions(model, arr)
        if contributions is not None:
            for name, value, contrib in zip(FEATURES, x, contributions):
                factors.append({"feature": FEATURE_LABELS[name], "value": value,
                                "contribution": round(float(contrib), 4)})
            factors.sort(key=lambda f: -abs(f["contribution"]))
        m = _state["metrics"] or {}
        return {
            "status": "ok",
            "probability_high_risk": round(prob, 3),
            "band": "HIGH" if prob >= 0.7 else "MODERATE" if prob >= 0.4 else "LOW",
            "top_factors": factors,
            "model": m.get("algorithm"),
            "training_samples": m.get("training_samples"),
            "loocv_accuracy": m.get("loocv_accuracy"),
            "disclaimer": DISCLAIMER,
        }
    except Exception as exc:
        return {"status": "error", "reason": f"{exc.__class__.__name__}: {exc}", "disclaimer": DISCLAIMER}
