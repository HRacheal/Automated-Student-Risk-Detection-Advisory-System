# backend/sequence_model.py
"""
EXPERIMENTAL Transformer sequence model - forecasts next-term academic decline from a student's
term-by-term history. Offline research only: NOT imported by the API, never creates alerts.

Task (fixed before training)
  input  : the student's terms 1..t (chronological), one vector per term:
           term GPA, has-GPA flag, credits attempted, credits earned, completion rate,
           #withdrawals (W), #fails (F), #incompletes (I)
  target : decline in term t+1 = term GPA drops >= 0.30 from term t, OR term GPA < 2.00,
           OR credit completion < 67 %  (the institution's advising thresholds)
  Each student contributes one sample per observed transition t -> t+1. The target term is
  never part of the input (no look-ahead).

Validation
  5-fold StratifiedGroupKFold grouped by STUDENT: all windows of a student are in the same fold,
  so the model is always tested on students it never saw. Feature scaling uses training-fold
  statistics only. Hyper-parameters are fixed below (not tuned on test folds). Two baselines are
  evaluated on the same folds: majority class and class-balanced logistic regression on the
  latest term's features.

Data sufficiency gate (MIN_*): training is refused - and no metric is reported - when the data
cannot support a meaningful evaluation. The only REAL sequential data (legacy
student_course_history) fails the gate; the synthetic RosarioSIS seed passes, so results on it
are labelled SYNTHETIC and are not evidence of real-world performance.

Run from backend/:  python -m sequence_model      (or via scripts/evaluate_models.py)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

from domain import LETTER_POINTS

BACKEND = Path(__file__).resolve().parent
SEED_FILE = BACKEND / "data" / "synthetic_student_demo_seed.json"
ARTIFACT = BACKEND / "reports" / "transformer_synthetic.pt"

FEATURE_NAMES = ["term_gpa", "has_gpa", "credits_attempted", "credits_earned", "completion_rate",
                 "withdrawals", "fails", "incompletes"]
TARGET_DEFINITION = ("Decline in the NEXT term: term GPA drops >= 0.30 from the latest term, or next-term GPA "
                     "< 2.00, or next-term credit completion < 67 %.")
MIN_SAMPLES, MIN_POSITIVES, MIN_STUDENTS, MIN_POSITIVE_STUDENTS = 50, 10, 10, 5
N_FOLDS, SEED = 5, 42
HYPERPARAMS = dict(model_dim=32, num_heads=4, num_layers=2, dropout=0.1, epochs=150, lr=1e-3, weight_decay=1e-2)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def _term_vector(rows: list[dict]) -> tuple[list[float], Optional[float], float]:
    """rows: [{grade_points, credits_attempted, credits_earned, kind}] of ONE term."""
    graded = [r for r in rows if r["grade_points"] is not None and r["kind"] not in ("withdrawn", "incomplete")]
    cr = sum(r["credits_attempted"] or 0 for r in graded)
    gpa = sum(r["grade_points"] * (r["credits_attempted"] or 0) for r in graded) / cr if cr else None
    attempted = sum(r["credits_attempted"] or 0 for r in rows)
    earned = sum(r["credits_earned"] or 0 for r in rows)
    completion = earned / attempted if attempted else 1.0
    vec = [gpa if gpa is not None else 0.0, 1.0 if gpa is not None else 0.0, attempted, earned, completion,
           sum(r["kind"] == "withdrawn" for r in rows), sum(r["kind"] == "failed" or (r["grade_points"] == 0.0)
                                                             for r in rows),
           sum(r["kind"] == "incomplete" for r in rows)]
    return vec, gpa, completion


def _declined(prev_gpa, next_gpa, next_completion) -> bool:
    return (prev_gpa - next_gpa >= 0.30) or next_gpa < 2.00 or next_completion < 0.67


def windows_from_terms(student_id: str, terms: list[list[dict]]) -> list[dict]:
    """terms: chronological list of term row-lists -> one sample per transition t -> t+1."""
    vecs = [_term_vector(t) for t in terms]
    out = []
    for i in range(1, len(vecs)):
        (_, prev_gpa, _), (_, next_gpa, next_comp) = vecs[i - 1], vecs[i]
        if prev_gpa is None or next_gpa is None:
            continue
        out.append({"student_id": student_id, "sequence": [v[0] for v in vecs[:i]],  # terms 1..t only
                    "target": int(_declined(prev_gpa, next_gpa, next_comp)), "target_term_index": i})
    return out


def load_synthetic_samples() -> list[dict]:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    order = {t["key"]: i for i, t in enumerate(seed["terms"])}
    samples = []
    for s in seed["students"]:
        by_term = defaultdict(list)
        for h in s["rosario"]["history"]:
            by_term[h["term"]].append(h)
        samples += windows_from_terms(str(s["student_id"]), [by_term[k] for k in sorted(by_term, key=order.get)])
    return samples


def load_legacy_samples(db) -> list[dict]:
    """The only REAL term-level history available (legacy student_course_history table)."""
    from models import StudentCourseHistory

    season = {"spring": 0, "summer": 1, "fall": 2}
    by_student: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in db.query(StudentCourseHistory).all():
        letter = (r.grade or "").strip().upper()
        kind = "withdrawn" if letter == "W" else "incomplete" if letter == "I" else "failed" if letter == "F" else "graded"
        by_student[r.student_id][r.semester or ""].append({
            "grade_points": LETTER_POINTS.get(letter), "credits_attempted": 3, "kind": kind,
            "credits_earned": 3 if LETTER_POINTS.get(letter, 0) >= 1.0 else 0})

    def key(sem: str):
        parts = sem.split()
        return (int(parts[-1]) if parts and parts[-1].isdigit() else 0, season.get(parts[0].lower(), 9) if parts else 9)

    samples = []
    for sid, terms in by_student.items():
        samples += windows_from_terms(str(sid), [terms[k] for k in sorted(terms, key=key)])
    return samples


def data_summary(samples: list[dict]) -> dict:
    students = {s["student_id"] for s in samples}
    pos_students = {s["student_id"] for s in samples if s["target"]}
    positives = sum(s["target"] for s in samples)
    checks = {
        f"samples >= {MIN_SAMPLES}": len(samples) >= MIN_SAMPLES,
        f"positive samples >= {MIN_POSITIVES}": positives >= MIN_POSITIVES,
        f"students >= {MIN_STUDENTS}": len(students) >= MIN_STUDENTS,
        f"students with a positive >= {MIN_POSITIVE_STUDENTS}": len(pos_students) >= MIN_POSITIVE_STUDENTS,
    }
    return {"samples": len(samples), "positives": positives, "negatives": len(samples) - positives,
            "students": len(students), "students_with_positive": len(pos_students),
            "sequence_lengths": sorted({len(s["sequence"]) for s in samples}),
            "gate": checks, "sufficient": all(checks.values())}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def build_model(input_dim: int, max_len: int):
    torch, nn = _torch()

    class StudentBehaviorTransformer(nn.Module):
        """Transformer encoder over padded term sequences; the last real term's encoding -> logit."""

        def __init__(self):
            super().__init__()
            d = HYPERPARAMS["model_dim"]
            self.embedding = nn.Linear(input_dim, d)
            self.position = nn.Embedding(max_len, d)
            layer = nn.TransformerEncoderLayer(d_model=d, nhead=HYPERPARAMS["num_heads"], dim_feedforward=2 * d,
                                               dropout=HYPERPARAMS["dropout"], batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, num_layers=HYPERPARAMS["num_layers"])
            self.head = nn.Linear(d, 1)

        def forward(self, x, lengths):
            positions = torch.arange(x.shape[1], device=x.device).unsqueeze(0)
            pad_mask = positions >= lengths.unsqueeze(1)                   # True = padding
            h = self.encoder(self.embedding(x) + self.position(positions), src_key_padding_mask=pad_mask)
            last = h[torch.arange(x.shape[0]), lengths - 1]                 # latest observed term
            return self.head(last).squeeze(-1)

    return StudentBehaviorTransformer()


def _pad(samples, mean, std, max_len):
    torch, _ = _torch()
    x = np.zeros((len(samples), max_len, len(FEATURE_NAMES)), dtype=np.float32)
    lengths = np.array([len(s["sequence"]) for s in samples])
    for i, s in enumerate(samples):
        seq = (np.asarray(s["sequence"], dtype=np.float32) - mean) / std
        x[i, :len(seq)] = seq
    return torch.tensor(x), torch.tensor(lengths)


def _norm_stats(samples):
    rows = np.asarray([v for s in samples for v in s["sequence"]], dtype=np.float32)
    std = rows.std(axis=0)
    return rows.mean(axis=0), np.where(std < 1e-6, 1.0, std)


def train_transformer(train: list[dict], seed: int, max_len: int):
    torch, nn = _torch()
    torch.manual_seed(seed)
    np.random.seed(seed)
    mean, std = _norm_stats(train)
    x, lengths = _pad(train, mean, std, max_len)
    y = torch.tensor([s["target"] for s in train], dtype=torch.float32)
    pos = float(y.sum())
    model = build_model(len(FEATURE_NAMES), max_len)
    opt = torch.optim.AdamW(model.parameters(), lr=HYPERPARAMS["lr"], weight_decay=HYPERPARAMS["weight_decay"])
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((len(y) - pos) / pos if pos else 1.0))
    model.train()
    for _ in range(HYPERPARAMS["epochs"]):
        opt.zero_grad()
        loss_fn(model(x, lengths), y).backward()
        opt.step()
    model.eval()
    return model, mean, std


def predict_transformer(model, mean, std, samples, max_len) -> np.ndarray:
    torch, _ = _torch()
    x, lengths = _pad(samples, mean, std, max_len)
    with torch.no_grad():
        return torch.sigmoid(model(x, lengths)).numpy()


def _last_term_features(samples) -> np.ndarray:
    """Baseline input: latest term's vector + GPA change from the previous term + number of terms."""
    out = []
    for s in samples:
        last = s["sequence"][-1]
        prev_gpa = s["sequence"][-2][0] if len(s["sequence"]) > 1 and s["sequence"][-2][1] else last[0]
        out.append(list(last) + [last[0] - prev_gpa, len(s["sequence"])])
    return np.asarray(out, dtype=float)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def _metrics(y, pred, prob) -> dict:
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix,
                                 f1_score, precision_score, recall_score, roc_auc_score)
    names = ["No decline", "Decline next term"]
    return {
        "accuracy_pct": round(100 * accuracy_score(y, pred), 1),
        "balanced_accuracy": round(balanced_accuracy_score(y, pred), 3),
        "precision": round(precision_score(y, pred, zero_division=0), 3),
        "recall": round(recall_score(y, pred, zero_division=0), 3),
        "f1": round(f1_score(y, pred, zero_division=0), 3),
        "roc_auc": round(roc_auc_score(y, prob), 3) if prob is not None and len(set(y)) == 2 else None,
        "confusion_matrix": {"labels": names, "rows_actual_cols_predicted": confusion_matrix(y, pred, labels=[0, 1]).tolist()},
        "classification_report_text": classification_report(y, pred, labels=[0, 1], target_names=names,
                                                            zero_division=0, digits=3),
    }


def cross_validate(samples: list[dict], seed: int = SEED) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = np.array([s["target"] for s in samples])
    groups = np.array([s["student_id"] for s in samples])
    max_len = max(len(s["sequence"]) for s in samples)
    prob_tf, prob_lr = np.zeros(len(y)), np.zeros(len(y))
    folds = []
    cv = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    for k, (tr, te) in enumerate(cv.split(np.zeros(len(y)), y, groups)):
        assert not set(groups[tr]) & set(groups[te]), "student leakage between train and test"
        train, test = [samples[i] for i in tr], [samples[i] for i in te]
        model, mean, std = train_transformer(train, seed + k, max_len)
        prob_tf[te] = predict_transformer(model, mean, std, test, max_len)
        lr = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))
        lr.fit(_last_term_features(train), y[tr])
        prob_lr[te] = lr.predict_proba(_last_term_features(test))[:, 1]
        folds.append({"fold": k + 1, "test_students": len(set(groups[te])), "test_samples": len(te),
                      "test_positives": int(y[te].sum())})
    pred_tf, pred_lr = (prob_tf >= 0.5).astype(int), (prob_lr >= 0.5).astype(int)
    return {
        "folds": folds,
        "transformer": _metrics(y, pred_tf, prob_tf),
        "baseline_logistic_regression": _metrics(y, pred_lr, prob_lr),
        "baseline_majority": _metrics(y, np.zeros(len(y), dtype=int), None),
    }


def run_experiment(db=None, save_artifact: bool = True) -> dict:
    """Full reproducible pipeline: gate -> grouped CV -> seed stability -> final model (synthetic)."""
    try:
        import torch  # noqa: F401
    except ImportError:
        return {"evaluable": False, "reason": "PyTorch is not installed (pip install torch)."}

    report = {"evaluable": False, "status": "EXPERIMENTAL - offline research only; not used by the API",
              "input_sequence": FEATURE_NAMES, "target": TARGET_DEFINITION, "hyperparameters": HYPERPARAMS,
              "validation": f"{N_FOLDS}-fold StratifiedGroupKFold grouped by student (no student in both train and test); "
                            "scaling fitted on training folds only; fixed hyper-parameters; threshold 0.5"}
    if db is not None:
        legacy = load_legacy_samples(db)
        report["real_data"] = {"source": "legacy student_course_history table", **data_summary(legacy),
                               "decision": "Not trained - fails the data sufficiency gate." if not data_summary(legacy)["sufficient"]
                               else "Sufficient"}
    samples = load_synthetic_samples()
    summary = data_summary(samples)
    report["synthetic_data"] = {"source": "backend/data/synthetic_student_demo_seed.json (fictitious students)", **summary}
    if not summary["sufficient"]:
        report["reason"] = "No dataset passes the data sufficiency gate; nothing was trained."
        return report

    cv = cross_validate(samples, SEED)
    stability = []
    for s in range(5):
        r = cross_validate(samples, s)["transformer"]
        stability.append({"seed": s, "f1": r["f1"], "roc_auc": r["roc_auc"]})
    f1s = [r["f1"] for r in stability]
    report.update(evaluable=True, trained_on="SYNTHETIC data", **cv,
                  seed_stability={"runs": stability, "f1_mean": round(float(np.mean(f1s)), 3),
                                  "f1_std": round(float(np.std(f1s)), 3)},
                  caveat=(f"Trained and evaluated on {summary['samples']} windows from {summary['students']} FICTITIOUS "
                          f"students ({summary['positives']} positives from {summary['students_with_positive']} students). "
                          "The synthetic histories were written to exercise the rule engine, so these numbers show the "
                          "pipeline works; they are NOT evidence of real-world predictive performance."))
    if save_artifact:
        import torch
        max_len = max(len(s["sequence"]) for s in samples)
        model, mean, std = train_transformer(samples, SEED, max_len)
        ARTIFACT.parent.mkdir(exist_ok=True)
        torch.save({"state_dict": model.state_dict(), "mean": mean.tolist(), "std": std.tolist(), "max_len": max_len,
                    "features": FEATURE_NAMES, "hyperparameters": HYPERPARAMS, "trained_on": "synthetic seed"}, ARTIFACT)
        report["artifact"] = str(ARTIFACT.relative_to(BACKEND))
    return report


if __name__ == "__main__":
    from database import SessionLocal

    db = SessionLocal()
    try:
        out = run_experiment(db)
    finally:
        db.rollback()
        db.close()
    print(json.dumps({k: v for k, v in out.items() if not k.endswith("_text")}, indent=1, default=str)[:6000])
