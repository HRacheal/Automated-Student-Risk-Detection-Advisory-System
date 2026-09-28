"""Guards for the experimental ML pipelines: no look-ahead, no student leakage, honest selection."""
import numpy as np
import pytest

import ml_models
import sequence_model as sm


def _term(gpa_points, kind="graded", credits=3):
    return [{"grade_points": gpa_points, "credits_attempted": credits,
             "credits_earned": credits if (gpa_points or 0) >= 1.0 else 0, "kind": kind}]


def test_windows_never_include_the_target_term():
    terms = [_term(3.5), _term(3.4), _term(2.8), _term(1.5)]
    windows = sm.windows_from_terms("S1", terms)
    assert [len(w["sequence"]) for w in windows] == [1, 2, 3]          # history up to t only
    assert [w["target"] for w in windows] == [0, 1, 1]                   # 3.4->2.8 drop, 1.5 < 2.0
    # the input of the last window ends with term 3 (GPA 2.8), never term 4
    assert windows[-1]["sequence"][-1][0] == pytest.approx(2.8)


def test_gate_refuses_tiny_real_dataset():
    samples = sm.windows_from_terms("A", [_term(3.0), _term(2.0)]) + sm.windows_from_terms("B", [_term(3.0), _term(3.0)])
    summary = sm.data_summary(samples)
    assert summary["samples"] == 2 and not summary["sufficient"]


def test_synthetic_folds_are_grouped_by_student():
    from sklearn.model_selection import StratifiedGroupKFold

    samples = sm.load_synthetic_samples()
    assert sm.data_summary(samples)["sufficient"]
    y = np.array([s["target"] for s in samples])
    groups = np.array([s["student_id"] for s in samples])
    for tr, te in StratifiedGroupKFold(n_splits=sm.N_FOLDS, shuffle=True, random_state=sm.SEED).split(y, y, groups):
        assert not set(groups[tr]) & set(groups[te])


def test_selection_prefers_minority_class_f1_over_accuracy():
    results = {
        "logistic_regression": {"f1_red": 0.8, "roc_auc": 0.9, "balanced_accuracy": 0.85, "accuracy": 0.80},
        "xgboost_original": {"f1_red": 0.0, "roc_auc": 0.8, "balanced_accuracy": 0.50, "accuracy": 0.95},
    }
    assert ml_models.select_best(results) == "logistic_regression"


def test_loocv_on_separable_toy_data_finds_the_minority_class():
    # like the legacy data: one feature (missed assignments) cleanly separates the minority class
    X = np.ones((16, 4))  # constant nuisance features (standardisation would rescale any noise)
    X[:, 3] = [0, 0, 1, 1, 2, 0, 1, 2, 3, 0, 1, 2, 5, 6, 7, 5]
    y = np.array([0] * 12 + [1] * 4)
    r = ml_models.loocv_evaluate("logistic_regression", X, y)
    assert r["recall_red"] == 1.0 and len(r["y_pred"]) == 16


def test_transformer_forward_pass_handles_padding():
    torch = pytest.importorskip("torch")
    samples = sm.windows_from_terms("S1", [_term(3.5), _term(3.4), _term(2.8)])
    model, mean, std = sm.train_transformer(samples + samples, seed=0, max_len=3)
    probs = sm.predict_transformer(model, mean, std, samples, max_len=3)
    assert probs.shape == (2,) and np.all((probs >= 0) & (probs <= 1))
    assert torch.is_tensor(sm._pad(samples, mean, std, 3)[0])
