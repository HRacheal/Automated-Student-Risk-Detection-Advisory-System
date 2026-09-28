"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Alert, StudentDetail, TestLab } from "@/lib/types";
import { SyncButton, useOnSync } from "@/components/AppShell";
import { Card, CardHeader, ErrorBanner, Loading, PageHeader, RiskBadge, Spinner, StatusBadge, btnSecondary, formatDateTime, inputCls } from "@/components/ui";

const OPEN = new Set(["active", "acknowledged"]);

/**
 * Where a scenario is in the enable -> sync -> alert -> disable -> sync -> auto-resolved cycle,
 * judged only from the stored alerts (what the last sync actually produced).
 */
function scenarioState(on: boolean, expected: string, alerts: Alert[], lastSyncedAt: string | undefined) {
  const open = alerts.find((a) => a.anomaly_type === expected && OPEN.has(a.status));
  const resolved = alerts.find((a) => a.anomaly_type === expected && a.status === "auto_resolved");
  if (on && open) return { text: "Detected ✓", cls: "bg-amber-100 text-amber-900" };
  if (on) return { text: "Waiting for Sync Data", cls: "bg-blue-50 text-blue-800" };
  if (open) return { text: "Turned off — run Sync Data to resolve", cls: "bg-blue-50 text-blue-800" };
  if (resolved && lastSyncedAt && resolved.resolved_at && resolved.resolved_at >= lastSyncedAt.slice(0, 16))
    return { text: "Auto-resolved ✓", cls: "bg-emerald-100 text-emerald-800" };
  return null;
}

export default function TestLabPage() {
  const [lab, setLab] = useState<TestLab | null>(null);
  const [studentId, setStudentId] = useState("DEMO-100");
  const [detail, setDetail] = useState<StudentDetail | null>(null);
  const [detailFor, setDetailFor] = useState<string | null>(null); // student the detail was loaded for
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadLab = useCallback(() => {
    api.testLab().then(setLab).catch((e) => setError(e.message));
  }, []);
  const loadStudent = useCallback(() => {
    api.student(studentId).then(setDetail).catch(() => setDetail(null)).finally(() => setDetailFor(studentId));
  }, [studentId]);
  const detailLoaded = detailFor === studentId;
  const reloadAll = useCallback(() => { loadLab(); loadStudent(); }, [loadLab, loadStudent]);

  useEffect(loadLab, [loadLab]);
  useEffect(loadStudent, [loadStudent]);
  useOnSync(reloadAll);

  const toggle = async (key: string, enabled: boolean) => {
    setBusyKey(key);
    setError(null);
    try {
      await api.toggleScenario(studentId, key, enabled);
      loadLab();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyKey(null);
    }
  };

  const reset = async () => {
    try {
      await api.resetScenarios();
      loadLab();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  if (!lab) return error ? <ErrorBanner message={error} /> : <Loading />;
  const active = new Set(lab.active[studentId] || []);
  const alerts = detail?.alerts || [];
  const openAlerts = alerts.filter((a) => OPEN.has(a.status));
  const recentlyResolved = alerts.filter((a) => a.status === "auto_resolved").slice(0, 5);
  const student = lab.students.find((s) => s.student_id === studentId);

  return (
    <>
      <PageHeader
        title="Test Lab"
        subtitle="Demonstrate the full detection flow with controlled local test data. Scenarios only change DEMO students stored locally — RosarioSIS and Moodle are never modified."
        actions={<button className={btnSecondary} onClick={reset} disabled={!lab.enabled}>Reset all scenarios</button>}
      />
      <ErrorBanner message={error} />
      {!lab.enabled && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          DEMO data is disabled (DEMO_DATA_ENABLED=false in backend/.env). Set it to true and restart the backend to use the Test Lab.
        </div>
      )}

      <Card className="mb-6 p-5">
        <ol className="grid gap-4 text-sm md:grid-cols-4">
          {[
            ["1", "Pick a DEMO student", "DEMO-100 starts as a healthy student (🟢 LOW)."],
            ["2", "Turn on a scenario", "Injects exactly one risk condition into that DEMO student."],
            ["3", "Sync Data", "The expected anomaly appears as an alert (status: Detected ✓)."],
            ["4", "Turn it off + Sync Data", "The alert auto-resolves (status: Auto-resolved ✓)."],
          ].map(([n, t, d]) => (
            <li key={n} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-900 text-xs font-bold text-gold-400">{n}</span>
              <div><p className="font-semibold text-slate-900">{t}</p><p className="text-xs text-slate-500">{d}</p></div>
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title="Risk scenarios"
            subtitle={`Each switch injects one condition into ${student?.full_name || studentId}'s local DEMO data`}
            action={
              <select className={`${inputCls} w-64`} value={studentId} onChange={(e) => setStudentId(e.target.value)} aria-label="DEMO student">
                {lab.students.map((s) => <option key={s.student_id} value={s.student_id}>{s.full_name} ({s.student_id})</option>)}
              </select>
            }
          />
          <ul className="divide-y divide-slate-100">
            {lab.scenarios.map((sc) => {
              const on = active.has(sc.key);
              const state = scenarioState(on, sc.expected_anomaly, alerts, detail?.last_synced_at);
              return (
                <li key={sc.key} className="flex items-center gap-4 px-5 py-3">
                  <button
                    role="switch"
                    aria-checked={on}
                    aria-label={sc.label}
                    onClick={() => toggle(sc.key, !on)}
                    disabled={busyKey === sc.key || !lab.enabled}
                    className={`relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50 ${on ? "bg-brand-700" : "bg-slate-300"}`}
                  >
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900">{sc.label}</p>
                    <p className="text-xs text-slate-500">Expected anomaly: {sc.expected_title}</p>
                  </div>
                  {busyKey === sc.key && <Spinner />}
                  {state && <span data-scenario-state={sc.key} className={`rounded px-2 py-0.5 text-[11px] font-semibold ${state.cls}`}>{state.text}</span>}
                  {on && <span className="rounded bg-brand-100 px-2 py-0.5 text-[11px] font-semibold text-brand-800">ON</span>}
                </li>
              );
            })}
          </ul>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Current result for this student" subtitle="As of the last sync — run Sync Data after changing scenarios" />
            <div className="px-5 py-4" data-testlab-result>
              {!detailLoaded ? <Loading /> : !detail ? (
                <p className="text-sm text-slate-500">Not synchronised yet. Click Sync Data.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <Link href={`/students/${encodeURIComponent(studentId)}`} className="font-semibold text-slate-900 hover:text-brand-700">{detail.student.full_name}</Link>
                    <RiskBadge level={detail.risk_level} size="lg" />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">Last synchronised {formatDateTime(detail.last_synced_at)}</p>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Open alerts</p>
                  <ul className="mt-1 space-y-2">
                    {openAlerts.length === 0 && <li className="text-sm text-emerald-700">🟢 No anomalies detected.</li>}
                    {openAlerts.map((a) => (
                      <li key={a.id} className="flex items-start gap-2 text-sm">
                        <RiskBadge level={a.severity} />
                        <span className="text-slate-800">{a.title}</span>
                      </li>
                    ))}
                  </ul>
                  {recentlyResolved.length > 0 && (
                    <>
                      <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Recently auto-resolved</p>
                      <ul className="mt-1 space-y-1">
                        {recentlyResolved.map((a) => (
                          <li key={a.id} className="flex items-center gap-2 text-xs text-slate-600">
                            <StatusBadge status={a.status} /> {a.title} <span className="text-slate-400">{formatDateTime(a.resolved_at)}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </>
              )}
              <div className="mt-4"><SyncButton /></div>
            </div>
          </Card>
          <Card className="p-5 text-sm text-slate-600">
            <p className="font-semibold text-slate-900">Testing with the live systems</p>
            <p className="mt-2">
              You can also create the conditions in RosarioSIS itself (e.g. schedule a student into courses, drop one, enter report-card
              grades, add a billing fee, or add a custom student field named “Major”) and in Moodle (enrol the student, set the Moodle
              user’s <em>ID number</em> to the RosarioSIS student ID, add assignments and quizzes). Then click Sync Data — the same rules run on the
              live data. The app only reads from these systems.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
