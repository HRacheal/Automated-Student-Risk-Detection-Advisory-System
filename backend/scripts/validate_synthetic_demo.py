"""
Validates REAL My Coach results (latest synchronised snapshots + open alerts in
the My Coach database) against backend/data/synthetic_student_demo_expectations.json.

Read-only: performs no writes. Run from backend/:
    python scripts/validate_synthetic_demo.py
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
from repository import latest_snapshot, open_alerts  # noqa: E402

EXPECT = json.loads((BACKEND / "data" / "synthetic_student_demo_expectations.json").read_text(encoding="utf-8"))


def main() -> int:
    db = SessionLocal()
    rows, failures = [], 0
    try:
        for e in EXPECT["students"]:
            sid = str(e["student_id"])
            snap = latest_snapshot(db, sid)
            if snap is None:
                rows.append((sid, e["group"], e["scenario"], "NOT SYNCED", "-", "FAIL", "student missing from My Coach"))
                failures += 1
                continue
            actual = {a.anomaly_type: a.severity for a in open_alerts(db, sid)}
            exp = e["current_code"]["indicators"]
            exp_risk = e["current_code"]["risk_level"]
            missing = {k: v for k, v in exp.items() if actual.get(k) != v}
            extra = {k: v for k, v in actual.items() if k not in exp}
            ok = not missing and not extra and snap.risk_level == exp_risk
            if not ok:
                failures += 1
            diff = []
            if missing:
                diff.append("expected-but-absent " + ", ".join(f"{k}:{v}" + (f" (got {actual[k]})" if k in actual else "")
                                                        for k, v in missing.items()))
            if extra:
                diff.append("unexpected " + ", ".join(f"{k}:{v}" for k, v in extra.items()))
            if snap.risk_level != exp_risk:
                diff.append(f"risk {snap.risk_level} != expected {exp_risk}")
            target = e["target"]
            note = ""
            if target["risk_level"] != exp_risk or target.get("add") or target.get("remove"):
                note = f"known gap -> target {target['risk_level']} (needs {', '.join(target.get('requires', []))})"
            rows.append((sid, e["group"], e["scenario"], snap.risk_level,
                         ", ".join(f"{k}:{v[0]}" for k, v in sorted(actual.items())) or "-",
                         "PASS" if ok else "FAIL", "; ".join(diff) or note))
    finally:
        db.close()
    print(f"{'ID':7} {'group':7} {'risk':9} {'result':6} actual indicators / discrepancy")
    for sid, grp, scen, risk, ind, res, info in rows:
        print(f"{sid:7} {grp:7} {risk:9} {res:6} {ind}")
        print(f"{'':32}scenario: {scen}" + (f"\n{'':32}{info}" if info else ""))
    print(f"\nRESULT: {len(rows) - failures}/{len(rows)} students match the current-code expectations")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
