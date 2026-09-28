"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Alert, Intervention } from "@/lib/types";
import { useOnSync } from "@/components/AppShell";
import AlertCard from "@/components/AlertCard";
import { Card, CardHeader, EmptyState, ErrorBanner, Loading, PageHeader, StatusBadge, formatDate, formatDateTime, inputCls } from "@/components/ui";

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || "";

export default function AlertsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = use(searchParams);
  const [tab, setTab] = useState<"alerts" | "interventions">("alerts");
  const [status, setStatus] = useState(first(sp.status) || "open");
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState(first(sp.anomaly_type));
  const [q, setQ] = useState("");
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [types, setTypes] = useState<{ type: string; title: string }[]>([]);
  const [interventions, setInterventions] = useState<Intervention[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api.alerts({ status, severity, anomaly_type: type, q })
      .then((r) => { setAlerts(r.alerts); setTypes(r.types); setError(null); })
      .catch((e) => setError(e.message));
    api.interventions().then((r) => setInterventions(r.interventions)).catch(() => undefined);
  }, [status, severity, type, q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  useOnSync(load);

  const completeIntervention = async (id: number) => {
    await api.updateIntervention(id, { status: "completed" });
    load();
  };

  return (
    <>
      <PageHeader title="Alerts & Interventions" subtitle="Review rule-based anomaly alerts, record advisor actions and follow the audit trail." />
      <ErrorBanner message={error} />

      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-sm shadow-sm">
        {(["alerts", "interventions"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded-md px-4 py-1.5 font-medium ${tab === t ? "bg-brand-900 text-white" : "text-slate-600 hover:text-slate-900"}`}>
            {t === "alerts" ? `Alerts${alerts ? ` (${alerts.length})` : ""}` : `Interventions${interventions ? ` (${interventions.length})` : ""}`}
          </button>
        ))}
      </div>

      {tab === "alerts" ? (
        <>
          <Card className="mb-4 p-4">
            <div className="grid gap-3 md:grid-cols-4">
              <input className={inputCls} placeholder="Search student or alert…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search alerts" />
              <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
                <option value="open">Open (active + acknowledged)</option>
                <option value="active">Active</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved by advisor</option>
                <option value="auto_resolved">Auto-resolved (condition cleared)</option>
                <option value="all">All history</option>
              </select>
              <select className={inputCls} value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
                <option value="">All severities</option>
                <option value="HIGH">🔴 High</option>
                <option value="MODERATE">🟡 Moderate</option>
                <option value="LOW">🟢 Low</option>
              </select>
              <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)} aria-label="Anomaly type">
                <option value="">All anomaly types</option>
                {types.map((t) => <option key={t.type} value={t.type}>{t.title}</option>)}
              </select>
            </div>
          </Card>
          {!alerts ? <Loading /> : alerts.length === 0 ? (
            <Card><EmptyState title="No alerts match these filters." /></Card>
          ) : (
            <div className="space-y-4">
              {alerts.map((a) => <AlertCard key={a.id} alert={a} onChanged={load} showStudent />)}
            </div>
          )}
        </>
      ) : (
        <Card>
          <CardHeader title="Intervention log" subtitle="All advisor actions across students" />
          {!interventions ? <Loading /> : interventions.length === 0 ? (
            <EmptyState title="No interventions logged yet.">Use “Log intervention” on an alert to record an action.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="px-5 py-2.5 font-medium">Student</th><th className="px-3 py-2.5 font-medium">Action</th><th className="px-3 py-2.5 font-medium">Status</th><th className="px-3 py-2.5 font-medium">Follow-up</th><th className="px-3 py-2.5 font-medium">Advisor</th><th className="px-5 py-2.5 font-medium">Logged</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {interventions.map((i) => (
                    <tr key={i.id} className="align-top">
                      <td className="px-5 py-3">
                        <Link href={`/students/${encodeURIComponent(i.student_id)}`} className="font-medium text-slate-900 hover:text-brand-700">{i.student_name || i.student_id}</Link>
                        {i.alert_id && <p className="text-xs text-slate-500">Alert #{i.alert_id}</p>}
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-slate-800">{i.action_type}</p>
                        {i.notes && <p className="text-xs text-slate-500">{i.notes}</p>}
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge status={i.status} />
                        {i.status !== "completed" && (
                          <button className="ml-2 text-xs font-medium text-brand-700 hover:underline" onClick={() => completeIntervention(i.id)}>Complete</button>
                        )}
                      </td>
                      <td className="px-3 py-3 text-slate-600">{formatDate(i.follow_up_date)}</td>
                      <td className="px-3 py-3 text-slate-600">{i.advisor}</td>
                      <td className="px-5 py-3 text-xs text-slate-500">{formatDateTime(i.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
