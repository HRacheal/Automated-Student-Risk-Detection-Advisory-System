"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { StudentSummary } from "@/lib/types";
import { useOnSync } from "@/components/AppShell";
import { Card, EmptyState, ErrorBanner, Loading, PageHeader, RiskBadge, SourceBadge, inputCls, timeAgo } from "@/components/ui";

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || "";

export default function StudentsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = use(searchParams);
  const [q, setQ] = useState(first(sp.q));
  const [risk, setRisk] = useState(first(sp.risk));
  const [source, setSource] = useState("");
  const [rows, setRows] = useState<StudentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api
      .students({ q, risk, source })
      .then((r) => {
        setRows(r.students);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [q, risk, source]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  useOnSync(load);

  return (
    <>
      <PageHeader title="Students" subtitle="Search and filter every student monitored in the latest synchronisation." />
      <ErrorBanner message={error} />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_180px_180px]">
          <input className={inputCls} placeholder="Search by name or student ID…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students" />
          <select className={inputCls} value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Risk level">
            <option value="">All risk levels</option>
            <option value="HIGH">🔴 High</option>
            <option value="MODERATE">🟡 Moderate</option>
            <option value="LOW">🟢 Low / normal</option>
          </select>
          <select className={inputCls} value={source} onChange={(e) => setSource(e.target.value)} aria-label="Data source">
            <option value="">All data sources</option>
            <option value="rosario">RosarioSIS</option>
            <option value="moodle">Moodle</option>
            <option value="demo">DEMO test data</option>
          </select>
        </div>
      </Card>

      <Card>
        {!rows ? (
          <Loading />
        ) : rows.length === 0 ? (
          <EmptyState title="No students match these filters.">Try clearing the search, or run Sync Data.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-medium">Student</th>
                  <th className="px-3 py-3 font-medium">Risk</th>
                  <th className="px-3 py-3 font-medium">Declared major</th>
                  <th className="px-3 py-3 font-medium">Standing</th>
                  <th className="px-3 py-3 text-right font-medium">GPA</th>
                  <th className="px-3 py-3 text-right font-medium">Courses</th>
                  <th className="px-3 py-3 text-right font-medium">Open alerts</th>
                  <th className="px-5 py-3 font-medium">Synced</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((s) => (
                  <tr key={s.student_id} className="hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <Link href={`/students/${encodeURIComponent(s.student_id)}`} className="font-medium text-slate-900 hover:text-brand-700">
                        {s.full_name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                        {s.student_id} {s.sources.map((src) => <SourceBadge key={src} source={src} />)}
                      </div>
                    </td>
                    <td className="px-3 py-3"><RiskBadge level={s.risk_level} /></td>
                    <td className="px-3 py-3 text-slate-700">
                      {s.major_field_available ? s.declared_major : <span className="text-slate-400" title="Not provided by the source system">unavailable</span>}
                    </td>
                    <td className="px-3 py-3 text-slate-700">{s.class_standing || <span className="text-slate-400">—</span>}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{s.cumulative_gpa?.toFixed(2) ?? <span className="text-slate-400">—</span>}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{s.current_course_count}</td>
                    <td className="px-3 py-3 text-right">
                      <span className="inline-flex gap-1 tabular-nums">
                        {s.open_alerts === 0 ? <span className="text-slate-400">0</span> : (
                          <>
                            {s.open_alerts_by_severity.HIGH ? <span title="High">🔴{s.open_alerts_by_severity.HIGH}</span> : null}
                            {s.open_alerts_by_severity.MODERATE ? <span title="Moderate">🟡{s.open_alerts_by_severity.MODERATE}</span> : null}
                            {s.open_alerts_by_severity.LOW ? <span title="Low">🟢{s.open_alerts_by_severity.LOW}</span> : null}
                          </>
                        )}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-500">{timeAgo(s.last_synced_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {rows && <p className="mt-3 text-xs text-slate-500">{rows.length} student(s)</p>}
    </>
  );
}
