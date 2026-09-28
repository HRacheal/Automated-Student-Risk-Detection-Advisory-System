"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DashboardSummary, Risk } from "@/lib/types";
import { SyncButton, useOnSync } from "@/components/AppShell";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  Loading,
  PageHeader,
  RISK_META,
  RiskBadge,
  SourceBadge,
  StatusBadge,
  formatDateTime,
  timeAgo,
} from "@/components/ui";

function StatTile({ label, value, hint, accent, href }: { label: string; value: number; hint?: string; accent?: string; href?: string }) {
  const body = (
    <Card className={`h-full border-l-4 p-5 transition hover:shadow-md ${accent || "border-l-brand-700"}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function RiskDistribution({ counts, total }: { counts: Record<Risk, number>; total: number }) {
  const order: Risk[] = ["HIGH", "MODERATE", "LOW"];
  return (
    <div>
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded bg-slate-100" role="img" aria-label="Risk distribution">
        {order.map((r) =>
          counts[r] ? (
            <div
              key={r}
              className={`${RISK_META[r].dot} first:rounded-l last:rounded-r`}
              style={{ width: `${(counts[r] / Math.max(total, 1)) * 100}%` }}
              title={`${RISK_META[r].label}: ${counts[r]} student(s)`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
        {order.map((r) => (
          <span key={r} className="inline-flex items-center gap-1.5">
            <span aria-hidden>{RISK_META[r].icon}</span>
            {RISK_META[r].label} <span className="font-semibold text-slate-900">{counts[r] || 0}</span>
            <span className="text-slate-400">({total ? Math.round(((counts[r] || 0) / total) * 100) : 0}%)</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.dashboard().then(setData).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useOnSync(load);

  if (error && !data) return <ErrorBanner message={error} />;
  if (!data) return <Loading label="Loading dashboard…" />;

  const maxType = Math.max(1, ...data.alerts_by_type.map((t) => t.count));
  const sources = data.last_sync?.sources || {};

  return (
    <>
      <PageHeader
        title="Advisor Dashboard"
        subtitle={
          data.last_sync
            ? `Risk picture as of the last synchronisation (${formatDateTime(data.last_sync.finished_at || data.last_sync.started_at)}).`
            : "No data has been synchronised yet."
        }
      />
      <ErrorBanner message={error} />

      {data.total_students === 0 ? (
        <Card>
          <EmptyState title="No students are being monitored yet">
            <p className="mb-4">Pull student records from RosarioSIS and Moodle to run the anomaly detection rules.</p>
            <div className="flex justify-center"><SyncButton /></div>
          </EmptyState>
        </Card>
      ) : (
        <>
          {/* KPI tiles */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
            <StatTile label="Students monitored" value={data.total_students} hint="From latest sync" href="/students" />
            <StatTile label="🔴 High risk" value={data.risk_counts.HIGH || 0} accent="border-l-red-500" href="/students?risk=HIGH" hint="Immediate follow-up" />
            <StatTile label="🟡 Moderate risk" value={data.risk_counts.MODERATE || 0} accent="border-l-amber-400" href="/students?risk=MODERATE" hint="Monitor closely" />
            <StatTile label="🟢 Low / normal" value={data.risk_counts.LOW || 0} accent="border-l-emerald-500" href="/students?risk=LOW" hint="No action needed" />
            <StatTile label="Active alerts" value={data.active_alerts} accent="border-l-gold-400" href="/alerts" hint="Open or acknowledged" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            {/* Requiring intervention */}
            <Card className="lg:col-span-2">
              <CardHeader
                title="Students requiring intervention"
                subtitle="High/moderate risk students with alerts that have no intervention logged yet"
                action={<Link href="/students" className="text-xs font-medium text-brand-700 hover:underline">View all students →</Link>}
              />
              {data.students_requiring_intervention.length === 0 ? (
                <EmptyState title="Every flagged alert has an intervention logged. 🎉" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-5 py-2.5 font-medium">Student</th>
                        <th className="px-3 py-2.5 font-medium">Risk</th>
                        <th className="px-3 py-2.5 font-medium">Major</th>
                        <th className="px-3 py-2.5 text-right font-medium">GPA</th>
                        <th className="px-5 py-2.5 text-right font-medium">Unaddressed alerts</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.students_requiring_intervention.map((s) => (
                        <tr key={s.student_id} className="hover:bg-slate-50">
                          <td className="px-5 py-3">
                            <Link href={`/students/${encodeURIComponent(s.student_id)}`} className="font-medium text-slate-900 hover:text-brand-700">
                              {s.full_name}
                            </Link>
                            <div className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
                              {s.student_id} {s.sources.map((src) => <SourceBadge key={src} source={src} />)}
                            </div>
                          </td>
                          <td className="px-3 py-3"><RiskBadge level={s.risk_level} /></td>
                          <td className="px-3 py-3 text-slate-600">{s.major_field_available ? s.declared_major : <span className="text-slate-400">n/a</span>}</td>
                          <td className="px-3 py-3 text-right tabular-nums text-slate-700">{s.cumulative_gpa?.toFixed(2) ?? "—"}</td>
                          <td className="px-5 py-3 text-right font-semibold tabular-nums text-slate-900">{s.unaddressed_alerts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {/* Risk distribution + anomaly types */}
            <div className="space-y-6">
              <Card>
                <CardHeader title="Risk distribution" subtitle={`${data.total_students} monitored students`} />
                <div className="px-5 py-4">
                  <RiskDistribution counts={data.risk_counts} total={data.total_students} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Open alerts by anomaly type" subtitle="Rule-based detections" />
                <div className="space-y-3 px-5 py-4">
                  {data.alerts_by_type.length === 0 && <p className="text-sm text-slate-500">No open alerts.</p>}
                  {data.alerts_by_type.map((t) => (
                    <Link key={t.type} href={`/alerts?anomaly_type=${t.type}`} className="group block" title={`${t.title}: ${t.count} open alert(s)`}>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-700 group-hover:text-brand-700">{t.title}</span>
                        <span className="font-semibold tabular-nums text-slate-900">{t.count}</span>
                      </div>
                      <div className="mt-1 h-2 rounded bg-slate-100">
                        <div className="h-2 rounded bg-brand-700 group-hover:bg-brand-800" style={{ width: `${(t.count / maxType) * 100}%` }} />
                      </div>
                    </Link>
                  ))}
                </div>
              </Card>
            </div>
          </div>

          {/* Recent anomalies */}
          <Card className="mt-6">
            <CardHeader
              title="Recent anomalies"
              subtitle="Most recently detected rule-based alerts"
              action={<Link href="/alerts?status=all" className="text-xs font-medium text-brand-700 hover:underline">Alert history →</Link>}
            />
            {data.recent_anomalies.length === 0 ? (
              <EmptyState title="No anomalies detected yet." />
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.recent_anomalies.map((a) => (
                  <li key={a.id} className={`border-l-4 px-5 py-3 ${RISK_META[a.severity].ring}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <RiskBadge level={a.severity} />
                      <span className="text-sm font-semibold text-slate-900">{a.title}</span>
                      <span className="text-sm text-slate-400">·</span>
                      <Link href={`/students/${encodeURIComponent(a.student_id)}`} className="text-sm text-brand-700 hover:underline">
                        {a.student_name || a.student_id}
                      </Link>
                      <span className="ml-auto flex items-center gap-2 text-xs text-slate-500">
                        <StatusBadge status={a.status} /> {timeAgo(a.detected_at)}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm text-slate-600">{a.description}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Source status */}
          {data.last_sync && (
            <Card className="mt-6">
              <CardHeader title="Data sources in the last sync" action={<Link href="/sync" className="text-xs font-medium text-brand-700 hover:underline">Sync history →</Link>} />
              <div className="grid gap-4 px-5 py-4 md:grid-cols-3">
                {Object.entries(sources).map(([name, s]) => (
                  <div key={name} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <SourceBadge source={name} />
                      <StatusBadge status={s.status} />
                    </div>
                    <p className="mt-2 text-xs text-slate-600">{s.message}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
