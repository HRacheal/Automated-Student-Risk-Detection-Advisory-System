"""
Reproducible, READ-ONLY evaluation of every model in My Coach.

  A. Experimental ML risk classifier (ml_models.py / analytics_engine.py) - advisory only
       data   : legacy `students` + `lms_activity` tables (advisor-assigned Red/Yellow/Green)
       target : Red (1) vs not Red (0)   - exactly what the served model predicts
       method : every candidate (Logistic Regression, Random Forest, XGBoost original, XGBoost
                configured for small data) with leave-one-out cross-validation on the same
                records; the served model is chosen by ml_models.SELECTION_RULE.
  B. Rule-based risk engine (anomaly_engine.py) - the production component that creates alerts
       data   : the 30 synthetic students (data/synthetic_student_demo_seed.json)
       truth  : the designed risk level in data/synthetic_student_demo_expectations.json ("target")
       B1     : in-memory run through the real RosarioSIS -> Moodle -> merge -> rules pipeline
                (same code path as scripts/dry_run_synthetic_seed.py, no writes)
       B2     : what the live system currently stores (latest synchronised snapshots)
  C. Transformer sequence model (sequence_model.py) - experimental next-term decline forecast,
     student-grouped cross-validation, with a data-sufficiency gate (real data: refused).

Nothing is written to any database, RosarioSIS or Moodle. Results are printed and saved to
backend/reports/model_performance.json (+ .txt), which the "Model Performance" page shows.

Run from backend/:   python scripts/evaluate_models.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import numpy as np  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

REPORT_DIR = BACKEND / "reports"
EXPECT = json.loads((BACKEND / "data" / "synthetic_student_demo_expectations.json").read_text(encoding="utf-8"))
RISK_LABELS = ["LOW", "MODERATE", "HIGH"]


def _pct(x):
    return None if x is None else round(100 * float(x), 1)


def _report(y_true, y_pred, labels, names):
    """Classification report + confusion matrix as plain JSON-friendly data."""
    rep = classification_report(y_true, y_pred, labels=labels, target_names=names, output_dict=True, zero_division=0)
    text = classification_report(y_true, y_pred, labels=labels, target_names=names, zero_division=0, digits=3)
    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()
    return rep, text, cm


# ---------------------------------------------------------------------------
# A. Experimental ML risk classifier - all candidates, same data, same LOOCV
# ---------------------------------------------------------------------------
XGB_DIAGNOSIS = (
    "The original XGBoost (50 trees, depth 2, learning rate 0.1, default min_child_weight=1) is trained on ~14 records "
    "with only 3 Red per leave-one-out fold. A split needs a hessian weight of at least 1 in each child, which 3 "
    "positives (p(1-p) ~ 0.2 each) cannot provide, so almost no tree can split (about 0.4 splits per tree). The "
    "probabilities stay near the 27% base rate (max 0.43 for a true Red record), below the 0.5 threshold, so Red is "
    "never predicted. The data itself is separable (every Red record has 4+ missed assignments): allowing splits "
    "(min_child_weight=0.1) and weighting the minority class fixes XGBoost.")


def evaluate_ml_classifiers() -> dict:
    try:
        import ml_models
        import xgboost  # noqa: F401
    except ImportError as exc:
        return {"evaluable": False, "reason": f"ML library not installed ({exc.name})"}

    from analytics_engine import FEATURES, load_training_data
    from database import SessionLocal

    db = SessionLocal()
    try:
        df = load_training_data(db)  # SELECT only
    finally:
        db.rollback()
        db.close()

    X = df[FEATURES].to_numpy(dtype=float)
    y = df["target"].to_numpy()
    n, positives = len(y), int(y.sum())
    if n < 6 or positives < 2 or positives > n - 2:
        return {"evaluable": False, "reason": f"Not enough labelled data (n={n}, Red={positives})"}

    names = ["Not Red (Green/Yellow)", "Red"]
    raw = {name: ml_models.loocv_evaluate(name, X, y) for name in ml_models.CANDIDATES}
    best = ml_models.select_best(raw)
    models = []
    for name, r in raw.items():
        _, text, cm = _report(y, r["y_pred"], [0, 1], names)
        models.append({
            "key": name, "label": ml_models.label(name), "selected": name == best,
            "accuracy_pct": _pct(r["accuracy"]), "balanced_accuracy": round(r["balanced_accuracy"], 3),
            "precision_red": round(r["precision_red"], 3), "recall_red": round(r["recall_red"], 3),
            "f1_red": round(r["f1_red"], 3), "f1_macro": round(r["f1_macro"], 3), "roc_auc": round(r["roc_auc"], 3),
            "confusion_matrix": {"labels": names, "rows_actual_cols_predicted": cm},
            "classification_report_text": text,
        })
    return {
        "evaluable": True,
        "role": "EXPERIMENTAL / advisory only. Shown as a probability on student pages; never creates alerts.",
        "dataset": "Legacy `students` + `lms_activity` tables in the My Coach PostgreSQL database (real labelled records)",
        "features": FEATURES,
        "classes": names,
        "class_counts": {names[0]: n - positives, names[1]: positives},
        "label_distribution": df["risk_level"].str.strip().value_counts().to_dict(),
        "validation": "Leave-one-out cross-validation (each record predicted once by a model trained on the other records)",
        "test_set_size": n,
        "baseline_majority_accuracy_pct": _pct(max(positives, n - positives) / n),
        "selection_rule": ml_models.SELECTION_RULE,
        "selected": best,
        "models": models,
        "xgboost_diagnosis": XGB_DIAGNOSIS,
        "caveat": f"Only {n} labelled records ({positives} Red), and the served model was chosen from {len(models)} "
                  f"candidates evaluated on these same records, so the selected model's scores are optimistic. They "
                  f"show which configuration works on this data, not real-world accuracy.",
    }


# ---------------------------------------------------------------------------
# C. Transformer sequence model (experimental)
# ---------------------------------------------------------------------------
def evaluate_transformer() -> dict:
    try:
        import sequence_model
    except ImportError as exc:
        return {"evaluable": False, "reason": f"Could not import the sequence model ({exc.name})"}
    from database import SessionLocal

    db = SessionLocal()
    try:
        return sequence_model.run_experiment(db)
    finally:
        db.rollback()
        db.close()


# ---------------------------------------------------------------------------
# B. Rule-based engine (production)
# ---------------------------------------------------------------------------
def _rule_metrics(pred_by_id: dict[str, str], source: str, note: str) -> dict:
    ids = [str(e["student_id"]) for e in EXPECT["students"]]
    truth = {str(e["student_id"]): e["target"]["risk_level"] for e in EXPECT["students"]}
    spec = {str(e["student_id"]): e["current_code"]["risk_level"] for e in EXPECT["students"]}
    evaluated = [i for i in ids if i in pred_by_id]
    if not evaluated:
        return {"evaluable": False, "source": source, "reason": note or "No predictions available"}

    y_true = [truth[i] for i in evaluated]
    y_pred = [pred_by_id[i] for i in evaluated]
    rep, text, cm = _report(y_true, y_pred, RISK_LABELS, RISK_LABELS)

    # Binary view used for advising: "at risk" = MODERATE or HIGH
    bt = [int(v != "LOW") for v in y_true]
    bp = [int(v != "LOW") for v in y_pred]
    brep, btext, bcm = _report(bt, bp, [0, 1], ["Not at risk (LOW)", "At risk (MODERATE/HIGH)"])

    groups = {str(e["student_id"]): e["group"] for e in EXPECT["students"]}
    scen = {str(e["student_id"]): e["scenario"] for e in EXPECT["students"]}
    return {
        "evaluable": True,
        "source": source,
        "note": note,
        "test_set_size": len(evaluated),
        "not_evaluated": [i for i in ids if i not in pred_by_id],
        "classes": RISK_LABELS,
        "accuracy_pct": _pct(accuracy_score(y_true, y_pred)),
        "precision_macro": round(precision_score(y_true, y_pred, labels=RISK_LABELS, average="macro", zero_division=0), 3),
        "recall_macro": round(recall_score(y_true, y_pred, labels=RISK_LABELS, average="macro", zero_division=0), 3),
        "f1_macro": round(f1_score(y_true, y_pred, labels=RISK_LABELS, average="macro", zero_division=0), 3),
        "f1_weighted": round(f1_score(y_true, y_pred, labels=RISK_LABELS, average="weighted", zero_division=0), 3),
        "roc_auc": None,
        "roc_auc_reason": "Not applicable: the rule engine outputs a fixed risk level, not a probability score.",
        "confusion_matrix": {"labels": RISK_LABELS, "rows_actual_cols_predicted": cm},
        "classification_report": rep,
        "classification_report_text": text,
        "binary_at_risk": {
            "accuracy_pct": _pct(accuracy_score(bt, bp)),
            "precision": round(precision_score(bt, bp, zero_division=0), 3),
            "recall": round(recall_score(bt, bp, zero_division=0), 3),
            "f1": round(f1_score(bt, bp, zero_division=0), 3),
            "confusion_matrix": {"labels": ["Not at risk (LOW)", "At risk (MODERATE/HIGH)"], "rows_actual_cols_predicted": bcm},
            "classification_report_text": btext,
        },
        "matches_engine_specification": sum(pred_by_id[i] == spec[i] for i in evaluated),
        "per_student": [{"student_id": i, "group": groups[i], "scenario": scen[i], "expected": truth[i],
                         "predicted": pred_by_id[i], "correct": truth[i] == pred_by_id[i]} for i in evaluated],
        "misclassified": [{"student_id": i, "scenario": scen[i], "expected": truth[i], "predicted": pred_by_id[i]}
                          for i in evaluated if truth[i] != pred_by_id[i]],
    }


def evaluate_rules_pipeline() -> dict:
    """B1: synthetic data through the real sync + rule code, in memory."""
    try:
        import dry_run_synthetic_seed as dry  # module import runs its structural checks only (no writes)
        _, _, _, _, results = dry.run_engine()
    except Exception as exc:
        return {"evaluable": False, "source": "pipeline",
                "reason": f"Pipeline run failed ({exc.__class__.__name__}: {exc}). It needs the RosarioSIS REST API "
                          f"(read-only reference tables) and the My Coach database (course catalogue)."}
    preds = {sid: res.risk_level for sid, (_, res) in results.items()}
    return _rule_metrics(preds, "pipeline",
                         "Seed data shaped exactly like RosarioSIS/Moodle API responses, run through the production "
                         "merge + anomaly rules in memory. Deterministic and reproducible.")


def evaluate_rules_stored() -> dict:
    """B2: the risk levels the live system currently shows (latest sync)."""
    from database import SessionLocal
    import models
    from repository import latest_snapshot

    db = SessionLocal()
    try:
        preds, runs = {}, set()
        for e in EXPECT["students"]:
            snap = latest_snapshot(db, str(e["student_id"]))
            if snap:
                preds[str(e["student_id"])] = snap.risk_level
                runs.add(snap.sync_run_id)
        run = db.query(models.SyncRun).filter(models.SyncRun.id.in_(runs)).order_by(models.SyncRun.id.desc()).first() \
            if runs else None
        src = {k: v.get("status") for k, v in (run.source_status or {}).items()} if run else {}
        note = (f"Latest stored snapshots (sync run #{run.id}, {run.status}; sources: "
                f"{', '.join(f'{k}={v}' for k, v in src.items())})." if run else "No synchronised snapshots.")
    finally:
        db.rollback()
        db.close()
    if src.get("moodle") and src["moodle"] != "ok":
        note += " Moodle was unavailable during this sync, so Moodle-based rules were skipped - re-sync with Moodle running."
    return _rule_metrics(preds, "stored", note)


# ---------------------------------------------------------------------------
def main() -> int:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "backend/scripts/evaluate_models.py",
        "rule_engine_pipeline": evaluate_rules_pipeline(),
        "rule_engine_stored": evaluate_rules_stored(),
        "ml_classifiers": evaluate_ml_classifiers(),
        "transformer": evaluate_transformer(),
    }

    lines = [f"MY COACH MODEL EVALUATION  ({report['generated_at']})", "=" * 78]
    x = report["ml_classifiers"]
    lines.append("A. Experimental ML risk classifier (advisory only - never creates alerts)")
    if x["evaluable"]:
        lines += [f"   Data: {x['dataset']}", f"   Classes: {x['classes']}   counts: {x['class_counts']}",
                  f"   Validation: {x['validation']}   test predictions per model: {x['test_set_size']}",
                  f"   Majority-class baseline accuracy: {x['baseline_majority_accuracy_pct']}%",
                  f"   Selection rule: {x['selection_rule']}"]
        for m in x["models"]:
            lines += [f"   {'>> SELECTED ' if m['selected'] else '   '}{m['label']}",
                      f"      accuracy {m['accuracy_pct']}%  balanced acc {m['balanced_accuracy']}  precision(Red) "
                      f"{m['precision_red']}  recall(Red) {m['recall_red']}  F1(Red) {m['f1_red']}  F1(macro) "
                      f"{m['f1_macro']}  ROC-AUC {m['roc_auc']}  confusion {m['confusion_matrix']['rows_actual_cols_predicted']}"]
        sel = next(m for m in x["models"] if m["selected"])
        lines += ["   Classification report (selected model):", sel["classification_report_text"],
                  f"   XGBoost diagnosis: {x['xgboost_diagnosis']}", f"   CAVEAT: {x['caveat']}"]
    else:
        lines.append(f"   Not evaluable: {x['reason']}")

    for key, title in (("rule_engine_pipeline", "B1. Rule engine - synthetic data through the real pipeline"),
                       ("rule_engine_stored", "B2. Rule engine - live stored results")):
        r = report[key]
        lines += ["=" * 78, title]
        if not r["evaluable"]:
            lines.append(f"   Not evaluable: {r['reason']}")
            continue
        lines += [f"   {r['note']}",
                  f"   Classes: {r['classes']}   test set: {r['test_set_size']} students",
                  f"   Accuracy {r['accuracy_pct']}%  Precision(macro) {r['precision_macro']}  "
                  f"Recall(macro) {r['recall_macro']}  F1(macro) {r['f1_macro']}  F1(weighted) {r['f1_weighted']}",
                  f"   ROC-AUC: {r['roc_auc_reason']}",
                  "   Confusion matrix (rows=actual, cols=predicted) LOW/MODERATE/HIGH:",
                  *[f"      {row}" for row in r["confusion_matrix"]["rows_actual_cols_predicted"]],
                  r["classification_report_text"],
                  f"   At-risk (MODERATE/HIGH) vs LOW: accuracy {r['binary_at_risk']['accuracy_pct']}%  "
                  f"precision {r['binary_at_risk']['precision']}  recall {r['binary_at_risk']['recall']}  "
                  f"F1 {r['binary_at_risk']['f1']}  matrix {r['binary_at_risk']['confusion_matrix']['rows_actual_cols_predicted']}",
                  f"   Matches the engine's own specification: {r['matches_engine_specification']}/{r['test_set_size']}"]
        lines += [f"   MISCLASSIFIED {m['student_id']}: expected {m['expected']}, got {m['predicted']} - {m['scenario']}"
                  for m in r["misclassified"]]
    t = report["transformer"]
    lines += ["=" * 78, "C. Transformer sequence model (EXPERIMENTAL, offline only)"]
    if t.get("real_data"):
        rd = t["real_data"]
        lines.append(f"   Real data ({rd['source']}): {rd['samples']} windows from {rd['students']} students -> {rd['decision']}")
    if not t["evaluable"]:
        lines.append(f"   Not evaluable: {t.get('reason')}")
    else:
        sd = t["synthetic_data"]
        lines += [f"   Target: {t['target']}", f"   Input per term: {', '.join(t['input_sequence'])}",
                  f"   Validation: {t['validation']}",
                  f"   Data: {sd['samples']} windows, {sd['positives']} positive, {sd['students']} synthetic students"]
        for key, name in (("transformer", "Transformer"), ("baseline_logistic_regression", "Baseline: logistic regression"),
                          ("baseline_majority", "Baseline: always 'no decline'")):
            m = t[key]
            lines.append(f"   {name:32} acc {m['accuracy_pct']}%  precision {m['precision']}  recall {m['recall']}  "
                         f"F1 {m['f1']}  ROC-AUC {m['roc_auc']}  confusion {m['confusion_matrix']['rows_actual_cols_predicted']}")
        lines += ["   Classification report (Transformer):", t["transformer"]["classification_report_text"],
                  f"   Seed stability (5 seeds): F1 {t['seed_stability']['f1_mean']} +/- {t['seed_stability']['f1_std']}",
                  f"   CAVEAT: {t['caveat']}"]

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "model_performance.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (REPORT_DIR / "model_performance.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved: {REPORT_DIR / 'model_performance.json'} and model_performance.txt")
    return 0


if __name__ == "__main__":
    np.random.seed(42)
    sys.exit(main())
