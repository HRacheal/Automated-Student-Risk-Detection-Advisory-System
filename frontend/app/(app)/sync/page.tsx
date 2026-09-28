"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { IntegrationStatus, MLStatus, SyncRun, SyncStatus } from "@/lib/types";
import { SyncButton, useOnSync } from "@/components/AppShell";
import { Card, CardHeader, EmptyState, ErrorBanner, Loading, PageHeader, SourceBadge, Spinner, StatusBadge, btnSecondary, formatDateTime, timeAgo } from "@/components/ui";

const SOURCE_INFO: Record<string, { title: string; short: string; role: string }> = {
  rosario: { title: "RosarioSIS", short: "RosarioSIS", role: "Academic records: students, enrollment, schedule, grades, billing" },
  moodle: { title: "Moodle LMS", short: "Moodle", role: "Learning activity: course access, assignments, submissions, quiz grades" },
  demo: { title: "Test Lab (DEMO)", short: "DEMO", role: "Controlled local test data — never written to RosarioSIS or Moodle" },
};

function duration(run: SyncRun) {
  if (!run.finished_at) return "—";
  const s = (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000;
  return `${s.toFixed(1)} s`;
}

/** Connected / Unavailable wording for a live connection check. */
function Connection({ status }: { status: string | undefined }) {
  if (!status) return <Spinner />;
  const ok = status === "ok";
  const label = ok ? "Connected" : status === "disabled" ? "Disabled" : status === "not_configured" ? "Not configured"
    : status === "error" ? "Error" : "Unavailable";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${
      ok ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : status === "disabled" || status === "not_configured"
        ? "bg-slate-100 text-slate-600 ring-slate-300" : "bg-red-50 text-red-700 ring-red-200"}`}>
      <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : status === "disabled" || status === "not_configured" ? "bg-slate-400" : "bg-red-500"}`} />
      {label}
    </span>
  );
}

function RunFacts({ run }: { run: SyncRun }) {
  const rows: [string, React.ReactNode][] = [
    ["Status", <StatusBadge key="s" status={run.status} />],
    ["Finished", `${formatDateTime(run.finished_at || run.started_at)} (${timeAgo(run.finished_at || run.started_at)})`],
    ["Records", Object.entries(run.sources).map(([k, s]) => `${SOURCE_INFO[k]?.short || k}: ${s.status === "ok" ? s.students : "not synchronised"}`).join(" · ")],
    ["Students joined (RosarioSIS ↔ Moodle)", run.joined_students ?? "not recorded"],
    ["Students analysed", run.students_analyzed],
    ["Alerts: new / resolved", `${run.new_alerts} / ${run.resolved_alerts}`],
  ];
  return (
    <dl className="space-y-1.5 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-start justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right text-slate-900">{v}</dd></div>
      ))}
      <p className="pt-1 text-xs text-slate-600">{run.summary}</p>
    </dl>
  );
}

export default function SyncPage() {
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [runs, setRuns] = useState<SyncRun[] | null>(null);
  const [ml, setMl] = useState<MLStatus | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchConnections = useCallback(() => {
    api.integrations()
      .then((s) => { setStatus(s); setCheckedAt(new Date().toISOString()); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setChecking(false));
  }, []);
  const check = () => {
    setChecking(true);
    fetchConnections();
  };
  const loadRuns = useCallback(() => {
    api.syncStatus().then(setSyncStatus).catch((e) => setError(e.message));
    api.syncRuns(25).then((r) => setRuns(r.runs)).catch((e) => setError(e.message));
    api.mlStatus().then(setMl).catch(() => undefined);
  }, []);
  const refreshAll = useCallback(() => { fetchConnections(); loadRuns(); }, [fetchConnections, loadRuns]);

  useEffect(refreshAll, [refreshAll]);
  useOnSync(refreshAll);

  const metrics = ml?.metrics as Record<string, string | number | null> | null;
  const last = syncStatus?.last;
  const lastOk = syncStatus?.last_successful;

  return (
    <>
      <PageHeader
        title="Data Sources & Sync"
        subtitle="Sync Data pulls RosarioSIS and Moodle, normalises the records, runs the anomaly rules and stores alerts and history."
        actions={<><button className={btnSecondary} onClick={check} disabled={checking}>{checking && <Spinner />} Test connections</button><SyncButton /></>}
      />
      <ErrorBanner message={error} />

      {/* Live connection status */}
      <div className="grid gap-4 md:grid-cols-3">
        {(["rosario", "moodle", "demo"] as const).map((key) => {
          const s = status?.[key];
          return (
            <Card key={key} className="p-5">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-slate-900">{SOURCE_INFO[key].title}</p>
                <Connection status={checking && !s ? undefined : s?.status} />
              </div>
              <p className="mt-1 text-xs text-slate-500">{SOURCE_INFO[key].role}</p>
              {s && <p className={`mt-3 text-sm ${s.status === "ok" || s.status === "disabled" ? "text-slate-700" : "text-red-700"}`}>{s.message}</p>}
            </Card>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-slate-400">Connections checked {checkedAt ? timeAgo(checkedAt) : "…"}. This checks reachability now; the cards below show what the last synchronisation actually retrieved.</p>

      {/* Last sync + last successful sync */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Last synchronisation" subtitle={syncStatus?.running ? "A synchronisation is running now…" : undefined} />
          <div className="px-5 py-4">{!syncStatus ? <Loading /> : last ? <RunFacts run={last} /> : <p className="text-sm text-slate-500">No synchronisation has been run yet.</p>}</div>
        </Card>
        <Card>
          <CardHeader title="Last successful synchronisation" subtitle="Every configured source (RosarioSIS and Moodle) synchronised" />
          <div className="px-5 py-4">
            {!syncStatus ? <Loading /> : lastOk ? <RunFacts run={lastOk} /> : <p className="text-sm text-slate-500">No fully successful synchronisation yet.</p>}
          </div>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Synchronisation history" subtitle="Each run is stored with the per-source outcome — click a row for details" />
        {!runs ? <Loading /> : runs.length === 0 ? <EmptyState title="No synchronisation has been run yet." /> : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Run</th><th className="px-3 py-2.5 font-medium">Started</th><th className="px-3 py-2.5 font-medium">Status</th>
                  <th className="px-3 py-2.5 font-medium">Sources</th><th className="px-3 py-2.5 text-right font-medium">Students</th>
                  <th className="px-3 py-2.5 text-right font-medium">Joined</th>
                  <th className="px-3 py-2.5 text-right font-medium">Anomalies</th><th className="px-3 py-2.5 text-right font-medium">New</th>
                  <th className="px-3 py-2.5 text-right font-medium">Resolved</th><th className="px-5 py-2.5 text-right font-medium">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((r) => (
                  <Fragment key={r.id}>
                    <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      <td className="px-5 py-3 font-medium text-slate-900">#{r.id}</td>
                      <td className="px-3 py-3 text-slate-600">{formatDateTime(r.started_at)}</td>
                      <td className="px-3 py-3"><StatusBadge status={r.status} /></td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(r.sources).map(([name, s]) => (
                            <span key={name} className="inline-flex items-center gap-1" title={`${s.status}: ${s.message}`}>
                              <SourceBadge source={name} />
                              <span className={`h-2 w-2 rounded-full ${s.status === "ok" ? "bg-emerald-500" : s.status === "not_configured" ? "bg-slate-300" : "bg-red-500"}`} />
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">{r.students_analyzed}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{r.joined_students ?? "—"}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{r.anomalies_detected}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{r.new_alerts}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{r.resolved_alerts}</td>
                      <td className="px-5 py-3 text-right tabular-nums text-slate-500">{duration(r)}</td>
                    </tr>
                    {expanded === r.id && (
                      <tr className="bg-slate-50">
                        <td colSpan={10} className="px-5 py-4">
                          <p className="mb-2 text-sm text-slate-700">{r.summary}</p>
                          {r.error && <p className="mb-2 text-sm text-red-700">Error: {r.error}</p>}
                          <div className="grid gap-3 md:grid-cols-3">
                            {Object.entries(r.sources).map(([name, s]) => (
                              <div key={name} className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
                                <div className="flex items-center justify-between"><SourceBadge source={name} /><StatusBadge status={s.status} /></div>
                                <p className="mt-2 text-slate-700">{s.message}</p>
                                {s.details && Object.keys(s.details).length > 0 && (
                                  <pre className="scroll-thin mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] text-slate-600">
                                    {JSON.stringify(s.details, null, 2)}
                                  </pre>
                                )}
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mt-6">
        <CardHeader title="Experimental ML model status" subtitle="Advisory only — never creates alerts. Full comparison on the Model Performance page." />
        <div className="px-5 py-4 text-sm">
          {!ml ? <Loading /> : !ml.trained ? (
            <p className="text-slate-600">Not trained: {ml.error || "the model trains in the background after the API starts."}</p>
          ) : (
            <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {Object.entries(metrics || {})
                .filter(([k, v]) => v !== null && typeof v !== "object" && !["warning", "trained_at"].includes(k))
                .map(([k, v]) => (
                  <div key={k}><dt className="text-xs uppercase tracking-wide text-slate-500">{k.replace(/_/g, " ")}</dt><dd className="mt-0.5 text-slate-900">{String(v)}</dd></div>
                ))}
              <div><dt className="text-xs uppercase tracking-wide text-slate-500">trained</dt><dd className="mt-0.5 text-slate-900">{formatDateTime(metrics?.trained_at as string)}</dd></div>
            </dl>
          )}
          {metrics?.warning && <p className="mt-3 text-xs text-amber-700">⚠ {String(metrics.warning)}</p>}
          <p className="mt-2 text-xs italic text-slate-500">{ml?.disclaimer}</p>
        </div>
      </Card>
    </>
  );
}
