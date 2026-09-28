"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  ConfusionMatrix,
  DataGate,
  MLClassifierEvaluation,
  ModelPerformanceReport,
  NotEvaluable,
  RuleEngineEvaluation,
  SequenceMetrics,
  TransformerEvaluation,
} from "@/lib/types";
import { Card, CardHeader, ErrorBanner, Loading, PageHeader, formatDateTime } from "@/components/ui";

const fmt = (v: number | null | undefined, d = 3) => (v == null ? "—" : v.toFixed(d));

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-xl font-semibold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    </div>
  );
}

function Matrix({ cm }: { cm: ConfusionMatrix }) {
  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-xs font-medium text-slate-500">actual ↓ / predicted →</th>
            {cm.labels.map((l) => <th key={l} className="px-3 py-1 text-xs font-medium text-slate-600">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {cm.rows_actual_cols_predicted.map((row, i) => (
            <tr key={cm.labels[i]}>
              <th className="px-2 py-1 text-left text-xs font-medium text-slate-600">{cm.labels[i]}</th>
              {row.map((v, j) => (
                <td key={j} className={`px-3 py-1.5 text-center font-semibold tabular-nums ${
                  i === j ? "bg-emerald-50 text-emerald-800" : v ? "bg-red-50 text-red-700" : "text-slate-400"}`}>
                  {v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Report({ text }: { text: string }) {
  return <pre className="scroll-thin overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{text}</pre>;
}

function Unavailable({ r }: { r: NotEvaluable | TransformerEvaluation }) {
  return <p className="px-5 py-4 text-sm text-slate-600">Not evaluable: {r.reason}</p>;
}

function SectionTitle({ tag, tone, title, children }: { tag: string; tone: "prod" | "exp"; title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 mt-8 first:mt-0">
      <div className="flex items-center gap-2">
        <span className={`rounded px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide ${
          tone === "prod" ? "bg-emerald-100 text-emerald-800" : "bg-violet-100 text-violet-800"}`}>{tag}</span>
        <h2 className="text-lg font-bold text-slate-900">{title}</h2>
      </div>
      <p className="mt-1 text-sm text-slate-600">{children}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
function RuleCard({ r, title }: { r: RuleEngineEvaluation | NotEvaluable; title: string }) {
  return (
    <Card>
      <CardHeader title={title} />
      {!r.evaluable ? <Unavailable r={r} /> : (
        <div className="space-y-4 px-5 py-4">
          <p className="text-sm text-slate-600">{r.note} Ground truth: the designed risk level of each of the {r.test_set_size} synthetic students.</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            <Metric label="Accuracy" value={`${r.accuracy_pct}%`} />
            <Metric label="Precision (macro)" value={fmt(r.precision_macro)} />
            <Metric label="Recall (macro)" value={fmt(r.recall_macro)} />
            <Metric label="F1 (macro)" value={fmt(r.f1_macro)} />
            <Metric label="F1 (weighted)" value={fmt(r.f1_weighted)} />
            <Metric label="Test size" value={`${r.test_set_size} students`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div><p className="mb-1 text-xs font-semibold text-slate-700">Confusion matrix (LOW / MODERATE / HIGH)</p><Matrix cm={r.confusion_matrix} /></div>
            <div><p className="mb-1 text-xs font-semibold text-slate-700">Classification report</p><Report text={r.classification_report_text} /></div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-1 text-xs font-semibold text-slate-700">
                At risk (MODERATE/HIGH) vs LOW — accuracy {r.binary_at_risk.accuracy_pct}%, precision {fmt(r.binary_at_risk.precision)},
                {" "}recall {fmt(r.binary_at_risk.recall)}, F1 {fmt(r.binary_at_risk.f1)}
              </p>
              <Matrix cm={r.binary_at_risk.confusion_matrix} />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold text-slate-700">Misclassified ({r.misclassified.length}) — documented known gaps</p>
              <ul className="space-y-1 text-xs text-slate-600">
                {r.misclassified.map((m) => (
                  <li key={m.student_id}><b>{m.student_id}</b>: expected {m.expected}, got {m.predicted} — {m.scenario}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="text-xs text-slate-500">ROC-AUC: {r.roc_auc_reason}</p>
        </div>
      )}
    </Card>
  );
}

function ClassifierCard({ r }: { r: MLClassifierEvaluation | NotEvaluable }) {
  if (!r.evaluable) return <Card><Unavailable r={r} /></Card>;
  const sel = r.models.find((m) => m.selected)!;
  return (
    <Card>
      <CardHeader title="Model comparison — same data, same target, same leave-one-out validation" subtitle={r.role} />
      <div className="space-y-4 px-5 py-4">
        <p className="text-sm text-slate-600">
          <b>Data:</b> {r.dataset}. <b>Target:</b> {r.classes[1]} vs {r.classes[0]}
          {" "}({Object.entries(r.class_counts).map(([k, v]) => `${v} ${k}`).join(", ")}). <b>Features:</b> {r.features.join(", ")}.
          {" "}<b>Validation:</b> {r.validation}; {r.test_set_size} test predictions per model. Majority-class baseline accuracy: {r.baseline_majority_accuracy_pct}%.
        </p>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Model</th><th className="px-3 py-2 text-right font-medium">Accuracy</th>
                <th className="px-3 py-2 text-right font-medium">Balanced acc.</th><th className="px-3 py-2 text-right font-medium">Precision (Red)</th>
                <th className="px-3 py-2 text-right font-medium">Recall (Red)</th><th className="px-3 py-2 text-right font-medium">F1 (Red)</th>
                <th className="px-3 py-2 text-right font-medium">ROC-AUC</th><th className="px-3 py-2 font-medium">Confusion [[TN, FP], [FN, TP]]</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {r.models.map((m) => (
                <tr key={m.key} className={m.selected ? "bg-emerald-50/60" : ""}>
                  <td className="px-3 py-2">{m.label}{m.selected && <span className="ml-2 rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-bold text-white">SERVED</span>}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.accuracy_pct}%</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(m.balanced_accuracy)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(m.precision_red)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(m.recall_red)}</td>
                  <td className="px-3 py-2 text-right font-semibold tabular-nums">{fmt(m.f1_red)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(m.roc_auc)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{JSON.stringify(m.confusion_matrix.rows_actual_cols_predicted)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-600"><b>Selection rule (declared before comparing):</b> {r.selection_rule}</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <div><p className="mb-1 text-xs font-semibold text-slate-700">Confusion matrix — {sel.label}</p><Matrix cm={sel.confusion_matrix} /></div>
          <div><p className="mb-1 text-xs font-semibold text-slate-700">Classification report — {sel.label}</p><Report text={sel.classification_report_text} /></div>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700"><b>Why the original XGBoost scored 0 on Red:</b> {r.xgboost_diagnosis}</div>
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">⚠ {r.caveat}</p>
      </div>
    </Card>
  );
}

function GateTable({ g, title }: { g: DataGate; title: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 text-xs">
      <p className="font-semibold text-slate-800">{title}</p>
      <p className="mt-1 text-slate-500">{g.source}</p>
      <p className="mt-1 text-slate-700">{g.samples} windows · {g.positives} positive · {g.students} students ({g.students_with_positive} with a positive)</p>
      <ul className="mt-2 space-y-0.5">
        {Object.entries(g.gate).map(([k, ok]) => <li key={k} className={ok ? "text-emerald-700" : "text-red-700"}>{ok ? "✓" : "✗"} {k}</li>)}
      </ul>
      <p className={`mt-2 font-semibold ${g.sufficient ? "text-emerald-700" : "text-red-700"}`}>{g.decision || (g.sufficient ? "Sufficient — trained (synthetic, experimental)" : "Not trained")}</p>
    </div>
  );
}

function SeqRow({ name, m, highlight }: { name: string; m: SequenceMetrics; highlight?: boolean }) {
  return (
    <tr className={highlight ? "bg-violet-50/60" : ""}>
      <td className="px-3 py-2">{name}</td>
      <td className="px-3 py-2 text-right tabular-nums">{m.accuracy_pct}%</td>
      <td className="px-3 py-2 text-right tabular-nums">{fmt(m.balanced_accuracy)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{fmt(m.precision)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{fmt(m.recall)}</td>
      <td className="px-3 py-2 text-right font-semibold tabular-nums">{fmt(m.f1)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{fmt(m.roc_auc)}</td>
      <td className="px-3 py-2 font-mono text-xs">{JSON.stringify(m.confusion_matrix.rows_actual_cols_predicted)}</td>
    </tr>
  );
}

function TransformerCard({ t }: { t: TransformerEvaluation }) {
  return (
    <Card>
      <CardHeader title="Transformer sequence model — next-term decline forecast" subtitle={t.status || "Experimental"} />
      <div className="space-y-4 px-5 py-4">
        {t.target && (
          <dl className="grid gap-2 text-sm md:grid-cols-2">
            <div><dt className="text-xs font-semibold text-slate-500">Target</dt><dd className="text-slate-800">{t.target}</dd></div>
            <div><dt className="text-xs font-semibold text-slate-500">Input sequence (one vector per term, terms 1..t)</dt><dd className="text-slate-800">{t.input_sequence?.join(", ")}</dd></div>
            <div className="md:col-span-2"><dt className="text-xs font-semibold text-slate-500">Validation (leakage controls)</dt><dd className="text-slate-800">{t.validation}</dd></div>
          </dl>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          {t.real_data && <GateTable g={t.real_data} title="Real term-level data" />}
          {t.synthetic_data && <GateTable g={t.synthetic_data} title="Synthetic term-level data" />}
        </div>
        {!t.evaluable ? <Unavailable r={t} /> : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Model (same student-grouped folds)</th><th className="px-3 py-2 text-right font-medium">Accuracy</th>
                    <th className="px-3 py-2 text-right font-medium">Balanced acc.</th><th className="px-3 py-2 text-right font-medium">Precision</th>
                    <th className="px-3 py-2 text-right font-medium">Recall</th><th className="px-3 py-2 text-right font-medium">F1</th>
                    <th className="px-3 py-2 text-right font-medium">ROC-AUC</th><th className="px-3 py-2 font-medium">Confusion</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  <SeqRow name="Transformer" m={t.transformer!} highlight />
                  <SeqRow name="Baseline: logistic regression (latest term)" m={t.baseline_logistic_regression!} />
                  <SeqRow name="Baseline: always “no decline”" m={t.baseline_majority!} />
                </tbody>
              </table>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div><p className="mb-1 text-xs font-semibold text-slate-700">Confusion matrix — Transformer</p><Matrix cm={t.transformer!.confusion_matrix} /></div>
              <div><p className="mb-1 text-xs font-semibold text-slate-700">Classification report — Transformer</p><Report text={t.transformer!.classification_report_text} /></div>
            </div>
            <p className="text-xs text-slate-600">
              Seed stability (5 seeds): F1 {fmt(t.seed_stability?.f1_mean)} ± {fmt(t.seed_stability?.f1_std)}
              {" "}({t.seed_stability?.runs.map((r) => fmt(r.f1)).join(", ")}). Hyper-parameters fixed in advance: {JSON.stringify(t.hyperparameters)}.
            </p>
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">⚠ {t.caveat}</p>
          </>
        )}
      </div>
    </Card>
  );
}

export default function ModelPerformancePage() {
  const [report, setReport] = useState<ModelPerformanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.modelPerformance().then(setReport).catch((e) => setError(e instanceof Error ? e.message : "Could not load the report"));
  }, []);

  return (
    <>
      <PageHeader
        title="Model Performance"
        subtitle={report
          ? <>Generated {formatDateTime(report.generated_at)} by <code>{report.generated_by}</code> from real, reproducible data — re-run it to refresh.</>
          : "Reproducible evaluation of the production rule engine and the experimental ML models."}
      />
      <ErrorBanner message={error} />
      {!report ? (!error && <Loading />) : report.ml_classifiers === undefined ? (
        <ErrorBanner message="This report was produced by an older version of the evaluation script. Run python scripts/evaluate_models.py in backend/." />
      ) : (
        <div>
          <SectionTitle tag="Production" tone="prod" title="Rule-based risk engine — creates every alert">
            14 transparent advising rules (anomaly_engine.py). Evaluated on the 30 synthetic students against their designed risk level.
          </SectionTitle>
          <div className="space-y-6">
            <RuleCard r={report.rule_engine_pipeline} title="Synthetic test set through the real sync pipeline (in memory)" />
            <RuleCard r={report.rule_engine_stored} title="Live stored results (latest synchronisation)" />
          </div>

          <SectionTitle tag="Experimental" tone="exp" title="ML risk classifier — advisory probability only">
            Shown as a supplementary probability on student pages. It never creates alerts and is not the production engine.
          </SectionTitle>
          <ClassifierCard r={report.ml_classifiers} />

          <SectionTitle tag="Experimental" tone="exp" title="Transformer sequence model — offline research">
            Not used by the application. Trained only when the data passes the sufficiency gate.
          </SectionTitle>
          <TransformerCard t={report.transformer} />
        </div>
      )}
    </>
  );
}
