"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MLPrediction, StudentDetail, StudentRecord } from "@/lib/types";
import { useOnSync } from "@/components/AppShell";
import AlertCard, { InterventionForm } from "@/components/AlertCard";
import ChatPanel from "@/components/ChatPanel";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  Loading,
  RISK_META,
  RiskBadge,
  SourceBadge,
  StatusBadge,
  btnSecondary,
  formatDate,
  formatDateTime,
} from "@/components/ui";

const Unavailable = ({ note = "Not available from source" }: { note?: string }) => (
  <span className="text-slate-400" title={note}>unavailable</span>
);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{children}</dd>
    </div>
  );
}

/** Single-series line chart of term GPA (0–4 scale) with per-point hover. */
function GpaTrend({ terms }: { terms: StudentRecord["term_gpas"] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (terms.length === 0) return <p className="text-sm text-slate-500">No graded terms available.</p>;
  const W = 520, H = 180, P = { l: 32, r: 16, t: 14, b: 28 };
  const x = (i: number) => P.l + (terms.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (terms.length - 1));
  const y = (g: number) => P.t + (1 - g / 4) * (H - P.t - P.b);
  const path = terms.map((t, i) => `${i ? "L" : "M"}${x(i)},${y(t.gpa)}`).join(" ");
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Term GPA trend">
        {[0, 1, 2, 3, 4].map((g) => (
          <g key={g}>
            <line x1={P.l} x2={W - P.r} y1={y(g)} y2={y(g)} stroke="#e2e8f0" strokeWidth={1} strokeDasharray={g === 2 ? "4 3" : undefined} />
            <text x={P.l - 8} y={y(g) + 4} textAnchor="end" className="fill-slate-400 text-[10px]">{g.toFixed(1)}</text>
          </g>
        ))}
        <text x={W - P.r} y={y(2) - 4} textAnchor="end" className="fill-slate-400 text-[9px]">probation 2.0</text>
        <path d={path} fill="none" stroke="#332c85" strokeWidth={2} strokeLinejoin="round" />
        {terms.map((t, i) => (
          <g key={t.term} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <circle cx={x(i)} cy={y(t.gpa)} r={14} fill="transparent" />
            <circle cx={x(i)} cy={y(t.gpa)} r={hover === i ? 6 : 4.5} fill="#332c85" stroke="#fff" strokeWidth={2} />
            <text x={x(i)} y={H - 8} textAnchor="middle" className="fill-slate-500 text-[10px]">{t.term}</text>
          </g>
        ))}
        {/* direct label on the latest point only */}
        <text x={x(terms.length - 1)} y={y(terms[terms.length - 1].gpa) - 10} textAnchor="middle" className="fill-slate-700 text-[11px] font-semibold">
          {terms[terms.length - 1].gpa.toFixed(2)}
        </text>
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md"
          style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(terms[hover].gpa) / H) * 100}%`, transform: "translate(-50%, -125%)" }}
        >
          <p className="font-semibold text-slate-900">{terms[hover].term}</p>
          <p className="text-slate-600">GPA {terms[hover].gpa.toFixed(2)} · {terms[hover].credits} credits</p>
        </div>
      )}
    </div>
  );
}

function MLPanel({ p }: { p: MLPrediction | null }) {
  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2">ML predictive risk <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-700">Experimental</span></span>}
        subtitle="A statistical estimate — separate from the rule-based anomalies above. It never creates alerts."
      />
      <div className="px-5 py-4 text-sm">
        {!p || p.status !== "ok" ? (
          <p className="text-slate-600">Not available: {p?.reason || "no prediction for this sync."}</p>
        ) : (
          <>
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-bold tabular-nums text-slate-900">{Math.round((p.probability_high_risk || 0) * 100)}%</span>
              <span className="text-slate-600">estimated probability of high risk</span>
              <span className="ml-auto text-xs text-slate-500">{p.band ? `${RISK_META[p.band].icon} ${p.band}` : null}</span>
            </div>
            {p.top_factors && p.top_factors.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">SHAP feature contributions</p>
                <ul className="mt-1 space-y-1">
                  {p.top_factors.map((f) => (
                    <li key={f.feature} className="flex justify-between text-xs text-slate-700">
                      <span>{f.feature} = {f.value}</span>
                      <span className="tabular-nums">{f.contribution > 0 ? "▲ raises" : f.contribution < 0 ? "▼ lowers" : "–"} {Math.abs(f.contribution).toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-500">
              {p.model}; trained on {p.training_samples} historical records; leave-one-out accuracy {p.loocv_accuracy}.
            </p>
          </>
        )}
        <p className="mt-2 text-xs italic text-slate-500">{p?.disclaimer}</p>
      </div>
    </Card>
  );
}

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [data, setData] = useState<StudentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"open" | "history">("open");
  const [showIntervention, setShowIntervention] = useState(false);

  const load = useCallback(() => {
    api.student(id).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);
  useOnSync(load);

  if (error && !data) return (<><ErrorBanner message={error} /><Link href="/students" className="text-sm text-brand-700">← Back to students</Link></>);
  if (!data) return <Loading label="Loading student record…" />;

  const s = data.student;
  const openAlerts = data.alerts.filter((a) => a.status === "active" || a.status === "acknowledged");
  const closedAlerts = data.alerts.filter((a) => !(a.status === "active" || a.status === "acknowledged"));
  const active = s.current_courses.filter((c) => c.status === "enrolled");
  const dropped = s.current_courses.filter((c) => c.status === "dropped");
  const withdrawals = [...dropped.map((c) => ({ code: c.code, when: `dropped ${formatDate(c.end_date)}`, term: c.term })),
    ...s.course_history.filter((g) => g.withdrawn).map((g) => ({ code: g.code, when: `grade ${g.grade_letter}`, term: g.term }))];
  const activeUnits = active.reduce((sum, c) => sum + (c.units || 0), 0);
  const missed = s.lms.assignments.filter((a) => a.status === "missed");
  const quizzes = s.lms.quizzes.filter((q) => q.percent !== null);
  const history = [...s.course_history].sort((a, b) => (b.term_order || 0) - (a.term_order || 0));

  return (
    <>
      <Link href="/students" className="text-sm text-brand-700 hover:underline">← All students</Link>

      {/* Header */}
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{s.full_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>ID {s.student_id}</span>
            {data.sources.map((src) => <SourceBadge key={src} source={src} />)}
            <span>· Synced {formatDateTime(data.last_synced_at)}</span>
          </div>
        </div>
        <div className="text-right">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Rule-based risk level</p>
          <RiskBadge level={data.risk_level} size="lg" />
        </div>
      </div>
      {s.is_demo && (
        <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50 px-4 py-2.5 text-sm text-violet-800">
          This is a <strong>DEMO</strong> student built from controlled local test data (Test Lab). It does not exist in RosarioSIS or Moodle.
        </div>
      )}
      <ErrorBanner message={error} />

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          {/* Profile */}
          <Card>
            <CardHeader title="Student information" />
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 px-5 py-4 md:grid-cols-4">
              <Field label="Declared major">{s.major_field_available ? s.declared_major : <Unavailable />}</Field>
              <Field label="Class standing">{s.class_standing || <Unavailable note="No completed units on record" />}</Field>
              <Field label="Completed units">{s.completed_units ?? <Unavailable />}</Field>
              <Field label="Cumulative GPA">{s.cumulative_gpa?.toFixed(2) ?? <Unavailable note="No graded courses on record" />}</Field>
              <Field label="Enrollment">
                {s.enrollment_status ? (
                  <span className={s.enrollment_status === "active" ? "text-emerald-700" : "font-semibold text-red-700"}>
                    {s.enrollment_status === "active" ? "Active" : "Withdrawn"}
                    {s.enrollment_note && <span className="block text-xs font-normal text-slate-500">{s.enrollment_note}</span>}
                  </span>
                ) : <Unavailable />}
              </Field>
              <Field label="School">{s.school || <Unavailable />}{s.grade_level ? <span className="text-xs text-slate-500"> · {s.grade_level}</span> : null}</Field>
              <Field label="Holds">{s.holds === null ? <Unavailable /> : s.holds.length ? <span className="text-red-700">{s.holds.join("; ")}</span> : "None"}</Field>
              <Field label="Tuition balance">
                {s.financial.available && s.financial.balance !== null ? (
                  <span className={s.financial.balance > 0 ? "font-semibold text-red-700" : ""}>
                    {s.financial.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    {s.financial.overdue_amount ? <span className="text-xs font-normal"> ({s.financial.overdue_amount.toLocaleString()} overdue)</span> : null}
                  </span>
                ) : <Unavailable />}
              </Field>
            </dl>
            {s.unavailable.length > 0 && (
              <div className="border-t border-slate-100 px-5 py-3">
                <p className="text-xs font-semibold text-slate-500">Data availability notes</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-slate-500">
                  {s.unavailable.map((u) => <li key={u}>{u}</li>)}
                </ul>
              </div>
            )}
          </Card>

          {/* Anomalies */}
          <Card>
            <CardHeader
              title="Detected anomalies"
              subtitle="Transparent advising rules applied to the synchronised data"
              action={
                <div className="flex rounded-lg border border-slate-200 p-0.5 text-xs">
                  {(["open", "history"] as const).map((t) => (
                    <button key={t} onClick={() => setTab(t)} className={`rounded-md px-3 py-1 font-medium ${tab === t ? "bg-brand-900 text-white" : "text-slate-600"}`}>
                      {t === "open" ? `Open (${openAlerts.length})` : `Resolved (${closedAlerts.length})`}
                    </button>
                  ))}
                </div>
              }
            />
            <div className="space-y-4 p-5">
              {(tab === "open" ? openAlerts : closedAlerts).length === 0 ? (
                <EmptyState title={tab === "open" ? "🟢 No active anomalies — the student is in good standing on every evaluated rule." : "No resolved alerts yet."} />
              ) : (
                (tab === "open" ? openAlerts : closedAlerts).map((a) => <AlertCard key={a.id} alert={a} onChanged={load} />)
              )}
            </div>
          </Card>

          {/* Current courses */}
          <Card>
            <CardHeader title={`Current courses${s.current_term ? ` — ${s.current_term}` : ""}`} subtitle={`${active.length} active · ${activeUnits} units`} />
            {s.current_courses.length === 0 ? (
              <EmptyState title={s.missing.includes("current_courses") ? "Course registrations are not available from the source." : "No course registrations for the current term."} />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr><th className="px-5 py-2 font-medium">Code</th><th className="px-3 py-2 font-medium">Title</th><th className="px-3 py-2 text-right font-medium">Units</th><th className="px-3 py-2 font-medium">Status</th><th className="px-5 py-2 font-medium">Dates</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {s.current_courses.map((c, i) => (
                      <tr key={`${c.code}-${i}`} className={c.status === "dropped" ? "text-slate-400" : ""}>
                        <td className="px-5 py-2.5 font-mono text-xs font-semibold">{c.code}</td>
                        <td className="px-3 py-2.5">{c.title || "—"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{c.units ?? "?"}</td>
                        <td className="px-3 py-2.5">{c.status === "dropped" ? <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700">Dropped</span> : <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700">Enrolled</span>}</td>
                        <td className="px-5 py-2.5 text-xs">{formatDate(c.start_date)}{c.end_date ? ` → ${formatDate(c.end_date)}` : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* GPA + history */}
          <Card>
            <CardHeader title="GPA trend & academic history" subtitle="Credit-weighted term GPA on a 4.0 scale" />
            <div className="grid gap-6 px-5 py-4 lg:grid-cols-5">
              <div className="lg:col-span-3"><GpaTrend terms={s.term_gpas} /></div>
              <div className="lg:col-span-2">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-1 font-medium">Term</th><th className="py-1 text-right font-medium">GPA</th><th className="py-1 text-right font-medium">Credits</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {s.term_gpas.map((t, i) => {
                      const prev = s.term_gpas[i - 1];
                      const delta = prev ? t.gpa - prev.gpa : 0;
                      return (
                        <tr key={t.term}>
                          <td className="py-1.5">{t.term}</td>
                          <td className="py-1.5 text-right tabular-nums">{t.gpa.toFixed(2)} {prev && <span className={`text-xs ${delta < 0 ? "text-red-600" : "text-emerald-600"}`}>{delta < 0 ? "▼" : "▲"}{Math.abs(delta).toFixed(2)}</span>}</td>
                          <td className="py-1.5 text-right tabular-nums text-slate-500">{t.credits}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            {history.length > 0 && (
              <details className="border-t border-slate-100">
                <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-brand-700">Course history ({history.length} records)</summary>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <tr><th className="px-5 py-2 font-medium">Term</th><th className="px-3 py-2 font-medium">Course</th><th className="px-3 py-2 font-medium">Grade</th><th className="px-3 py-2 text-right font-medium">Points</th><th className="px-5 py-2 text-right font-medium">Credits earned</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {history.map((g, i) => (
                        <tr key={i}>
                          <td className="px-5 py-2 text-slate-500">{g.term || "—"}</td>
                          <td className="px-3 py-2"><span className="font-mono text-xs font-semibold">{g.code}</span> {g.title && <span className="text-slate-500">{g.title}</span>}</td>
                          <td className={`px-3 py-2 font-semibold ${g.withdrawn ? "text-amber-700" : g.incomplete ? "text-blue-700" : g.passed === false ? "text-red-700" : (g.grade_points ?? 4) < 2 ? "text-amber-700" : "text-slate-800"}`}>{g.grade_letter || g.grade_percent || "—"}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{g.grade_points?.toFixed(1) ?? "—"}</td>
                          <td className="px-5 py-2 text-right tabular-nums">{g.credits_earned ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </Card>

          {/* LMS */}
          <Card>
            <CardHeader title="LMS engagement (Moodle)" />
            {!s.lms.available ? (
              <EmptyState title="Moodle data is not available for this student.">No linked Moodle account, or Moodle was unreachable during the sync.</EmptyState>
            ) : (
              <div className="grid gap-6 px-5 py-4 md:grid-cols-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Last course access</p>
                  <p className={`mt-1 text-2xl font-bold ${s.lms.days_since_last_access === null || s.lms.days_since_last_access >= 14 ? "text-red-700" : "text-slate-900"}`}>
                    {s.lms.days_since_last_access === null ? "Never" : s.lms.days_since_last_access === 0 ? "Today" : `${s.lms.days_since_last_access} days ago`}
                  </p>
                  <p className="text-xs text-slate-500">{s.lms.courses.length} Moodle course(s): {s.lms.courses.join(", ")}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Assignments</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {s.lms.assignments.length - missed.length}<span className="text-base font-normal text-slate-500">/{s.lms.assignments.length} submitted</span>
                  </p>
                  {missed.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-xs text-red-700">
                      {missed.map((a, i) => <li key={i}>✕ {a.course}: {a.name} (due {formatDate(a.due_date)})</li>)}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quiz scores</p>
                  {quizzes.length === 0 ? <p className="mt-1 text-sm text-slate-500">No graded quizzes</p> : (
                    <>
                      <p className="mt-1 text-2xl font-bold text-slate-900">{Math.round(quizzes.reduce((a, q) => a + (q.percent || 0), 0) / quizzes.length)}%<span className="text-base font-normal text-slate-500"> average</span></p>
                      <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                        {quizzes.map((q, i) => <li key={i} className={(q.percent || 0) < 50 ? "text-red-700" : ""}>{q.course}: {q.name} — {q.percent}%</li>)}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Advising assistant" subtitle="Rule-based answers from this student's data" />
            <ChatPanel studentId={s.student_id} studentName={s.full_name} height="h-80" />
          </Card>

          <MLPanel p={data.ml_prediction} />

          <Card>
            <CardHeader title="Withdrawals" subtitle={`${withdrawals.length} on record`} />
            <div className="px-5 py-3 text-sm">
              {withdrawals.length === 0 ? <p className="text-slate-500">No withdrawals on record.</p> : (
                <ul className="space-y-1">{withdrawals.map((w, i) => <li key={i}><span className="font-mono text-xs font-semibold">{w.code}</span> <span className="text-slate-500">— {w.when}{w.term ? `, ${w.term}` : ""}</span></li>)}</ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Interventions"
              action={<button className={btnSecondary} onClick={() => setShowIntervention((v) => !v)}>+ New</button>}
            />
            <div className="space-y-3 px-5 py-4">
              {showIntervention && (
                <InterventionForm studentId={s.student_id} onCancel={() => setShowIntervention(false)} onSaved={() => { setShowIntervention(false); load(); }} />
              )}
              {data.interventions.length === 0 && !showIntervention && <p className="text-sm text-slate-500">No interventions logged.</p>}
              {data.interventions.map((i) => (
                <div key={i.id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-slate-900">{i.action_type}</p>
                    <StatusBadge status={i.status} />
                  </div>
                  {i.notes && <p className="mt-1 text-sm text-slate-600">{i.notes}</p>}
                  <p className="mt-1 text-xs text-slate-500">
                    {i.advisor} · {formatDateTime(i.created_at)}{i.follow_up_date ? ` · follow-up ${formatDate(i.follow_up_date)}` : ""}
                    {i.alert_id ? ` · alert #${i.alert_id}` : ""}
                  </p>
                  {i.status !== "completed" && (
                    <button className="mt-2 text-xs font-medium text-brand-700 hover:underline" onClick={() => api.updateIntervention(i.id, { status: "completed" }).then(load)}>
                      Mark completed
                    </button>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Alert & intervention history" subtitle="Audit trail" />
            <ol className="scroll-thin max-h-80 space-y-3 overflow-y-auto px-5 py-4">
              {data.events.length === 0 && <p className="text-sm text-slate-500">No events yet.</p>}
              {data.events.map((e) => {
                const alert = data.alerts.find((a) => a.id === e.alert_id);
                return (
                  <li key={e.id} className="relative border-l-2 border-slate-200 pl-4">
                    <span className="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-brand-700" />
                    <p className="text-xs text-slate-500">{formatDateTime(e.created_at)} · {e.actor}</p>
                    <p className="text-sm text-slate-800"><span className="font-medium capitalize">{e.event_type.replace(/_/g, " ")}</span>{alert ? ` — ${alert.title}` : ""}</p>
                    {e.detail && <p className="text-xs text-slate-500">{e.detail}</p>}
                  </li>
                );
              })}
            </ol>
          </Card>

          <Card>
            <CardHeader title="Rule coverage" subtitle={`${data.rules_evaluated.length} evaluated · ${data.rules_skipped.length} skipped (data unavailable)`} />
            <div className="px-5 py-3 text-xs">
              {data.rules_skipped.length > 0 && (
                <ul className="space-y-1.5">
                  {data.rules_skipped.map((r) => (
                    <li key={r.rule}><span className="font-medium text-slate-700">{r.title}:</span> <span className="text-slate-500">{r.reason}</span></li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-slate-500">Evaluated: {data.rules_evaluated.map((r) => r.title).join(", ") || "none"}</p>
            </div>
          </Card>

          {data.risk_history.length > 1 && (
            <Card>
              <CardHeader title="Risk level over syncs" />
              <div className="flex flex-wrap gap-1 px-5 py-4">
                {data.risk_history.map((h) => (
                  <span key={h.sync_run_id} title={`Sync #${h.sync_run_id} · ${formatDateTime(h.synced_at)} · ${h.risk_level}`} className="cursor-default text-base">
                    {RISK_META[h.risk_level].icon}
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
