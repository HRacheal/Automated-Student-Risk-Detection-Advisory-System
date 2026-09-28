"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, API_BASE_URL, api, homeFor } from "@/lib/api";
import type { AdminOverview, IntegrationStatus } from "@/lib/types";
import { SyncButton, useOnSync } from "@/components/AppShell";
import { Card, CardHeader, ErrorBanner, Loading, PageHeader, RiskBadge, Spinner, StatusBadge, btnSecondary, formatDateTime, timeAgo } from "@/components/ui";

function Pill({ ok, okText = "OK", badText = "Not configured", tone }: { ok: boolean; okText?: string; badText?: string; tone?: "warn" }) {
  const cls = ok ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : tone === "warn" ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-red-50 text-red-700 ring-red-200";
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}>{ok ? okText : badText}</span>;
}

function Row({ label, detail, children }: { label: string; detail?: string; children: React.ReactNode }) {
  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div>
        <p className="text-sm text-slate-800">{label}</p>
        {detail && <p className="text-xs text-slate-500">{detail}</p>}
      </div>
      <div className="shrink-0 text-right text-sm">{children}</div>
    </li>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Role comes from the backend session check, not from localStorage.
  useEffect(() => {
    api.me()
      .then((u) => (u.role === "admin" ? setAllowed(true) : router.replace(homeFor(u.role))))
      .catch(() => undefined);
  }, [router]);

  const checkSources = useCallback(() => {
    api.integrations().then(setStatus).catch((e) => setError(e.message)).finally(() => setChecking(false));
  }, []);

  const load = useCallback(() => {
    api.adminOverview()
      .then((o) => { setOverview(o); setLoadedAt(new Date().toISOString()); setError(null); })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) router.replace("/dashboard");
        else setError(e instanceof Error ? e.message : "Could not load the overview");
      });
  }, [router]);

  const reload = useCallback(() => { load(); checkSources(); }, [load, checkSources]);
  const refresh = () => {
    setChecking(true);
    reload();
  };

  useEffect(() => {
    if (allowed) reload();
  }, [allowed, reload]);
  useOnSync(reload);

  if (!allowed) return <Loading label="Checking permissions…" />;

  const o = overview;
  const rosarioOk = status?.rosario.status === "ok";
  const moodleOk = status?.moodle.status === "ok";
  // A source that is not configured on THIS server (e.g. the public deployment, where RosarioSIS and
  // Moodle live on the campus/local machine) is not a failure; only configured-but-unreachable ones are.
  const rosarioDown = !!status && !rosarioOk && status.rosario.status !== "not_configured";
  const moodleDown = !!status && !moodleOk && status.moodle.status !== "not_configured";
  const sourcesLocalOnly = !!status && status.rosario.status === "not_configured" && status.moodle.status === "not_configured";
  const healthy = o && status ? o.database === "ok" && !rosarioDown && !moodleDown : null;

  return (
    <>
      <PageHeader
        title="Administration"
        subtitle="Live system status, data sources, synchronisation and configuration. Secret values (passwords, tokens, JWT secret, database URL) are never shown."
        actions={
          <>
            <button className={btnSecondary} onClick={refresh} disabled={checking}>
              {checking && <Spinner />} Refresh status
            </button>
            <SyncButton />
          </>
        }
      />
      <ErrorBanner message={error} />

      {!o ? (
        !error && <Loading />
      ) : (
        <>
          {/* Health banner */}
          <div className={`mb-6 rounded-xl border px-5 py-4 ${healthy == null ? "border-slate-200 bg-white"
            : healthy ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-base font-semibold text-slate-900">
                System health: {healthy == null ? "checking…" : healthy ? "All systems operational" : "Degraded"}
              </p>
              {checking && <Spinner />}
              <span className="ml-auto text-xs text-slate-500">
                Signed in as <b>{o.viewer.name || o.viewer.email}</b> · role <b className="uppercase">{o.viewer.role}</b> · refreshed {loadedAt ? timeAgo(loadedAt) : "—"}
              </span>
            </div>
            {healthy === false && (
              <ul className="mt-2 list-disc pl-5 text-sm text-amber-900">
                {o.database !== "ok" && <li>The My Coach database is unavailable.</li>}
                {rosarioDown && <li>RosarioSIS: {status?.rosario.message}</li>}
                {moodleDown && <li>Moodle: {status?.moodle.message} (start Moodle&apos;s bundled Apache and MariaDB, then sync).</li>}
              </ul>
            )}
            {sourcesLocalOnly && (
              <p className="mt-2 text-sm text-slate-700">
                RosarioSIS and Moodle are not connected to this server (they run on the campus/local machine). Student data shown here
                comes from the shared database, updated when Sync Data is run on the local My Coach instance. Sync Data on this server
                refreshes Test Lab (DEMO) data only.
              </p>
            )}
          </div>

          {/* Key numbers */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-5">
              <p className="text-xs uppercase tracking-wide text-slate-500">Students monitored</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{o.usage.students_monitored}</p>
              {o.usage.demo_students > 0 && <p className="text-xs text-violet-700">incl. {o.usage.demo_students} DEMO student(s)</p>}
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-wide text-slate-500">Risk distribution</p>
              <div className="mt-2 flex flex-wrap gap-3">
                {(["HIGH", "MODERATE", "LOW"] as const).map((r) => (
                  <span key={r} className="flex items-center gap-1.5"><RiskBadge level={r} /><b className="tabular-nums">{o.usage.risk_counts[r] ?? 0}</b></span>
                ))}
              </div>
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-wide text-slate-500">Open alerts</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{o.usage.open_alerts}</p>
              <p className="text-xs text-red-700">{o.usage.open_high_alerts} HIGH severity</p>
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-wide text-slate-500">Interventions / sync runs</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{o.usage.interventions} / {o.usage.sync_runs}</p>
            </Card>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            {/* Services */}
            <Card>
              <CardHeader title="Services" subtitle="Live checks" />
              <ul className="divide-y divide-slate-100 px-5">
                <Row label="My Coach API" detail={`${API_BASE_URL} · v${o.api.version}`}><Pill ok={o.api.status === "ok"} okText="Online" badText="Offline" /></Row>
                <Row label="My Coach database" detail="PostgreSQL (connection string hidden)"><Pill ok={o.database === "ok"} okText="Connected" badText="Unavailable" /></Row>
                <Row label="RosarioSIS" detail={status?.rosario.message}>
                  {status ? <Pill ok={rosarioOk} okText="Connected" tone={rosarioDown ? undefined : "warn"}
                    badText={rosarioDown ? "Unavailable" : "Not on this server"} /> : <Spinner />}
                </Row>
                <Row label="Moodle LMS" detail={status?.moodle.message}>
                  {status ? <Pill ok={moodleOk} okText="Connected" tone={moodleDown ? undefined : "warn"}
                    badText={moodleDown ? "Unavailable" : "Not on this server"} /> : <Spinner />}
                </Row>
              </ul>
            </Card>

            {/* Sync */}
            <Card>
              <CardHeader title="Synchronisation" action={<Link href="/sync" className="text-xs font-medium text-brand-700 hover:underline">Data Sources & Sync →</Link>} />
              <ul className="divide-y divide-slate-100 px-5">
                <Row label="Current state">{o.sync_running ? <span className="inline-flex items-center gap-1 text-blue-700"><Spinner /> running</span> : "idle"}</Row>
                <Row label="Last sync" detail={o.last_sync?.summary}>
                  {o.last_sync ? <span className="flex flex-col items-end gap-1"><StatusBadge status={o.last_sync.status} /><span className="text-xs text-slate-500">#{o.last_sync.id} · {formatDateTime(o.last_sync.finished_at || o.last_sync.started_at)}</span></span> : "never"}
                </Row>
                <Row label="Last successful sync">
                  {o.last_successful_sync ? <span className="text-xs text-slate-700">#{o.last_successful_sync.id} · {formatDateTime(o.last_successful_sync.finished_at)} ({timeAgo(o.last_successful_sync.finished_at)})</span> : "none yet"}
                </Row>
                {o.last_sync && (
                  <Row label="Last run results">
                    <span className="text-xs text-slate-700">{o.last_sync.students_analyzed} analysed · {o.last_sync.joined_students ?? "—"} joined · {o.last_sync.new_alerts} new / {o.last_sync.resolved_alerts} resolved</span>
                  </Row>
                )}
              </ul>
            </Card>

            {/* Configuration */}
            <Card>
              <CardHeader title="Configuration" subtitle="Presence only — values stay on the server" />
              <ul className="divide-y divide-slate-100 px-5">
                <Row label="Database URL"><Pill ok={o.configuration.database_configured} okText="Set" /></Row>
                <Row label="JWT signing secret"><Pill ok={o.configuration.jwt_configured} okText="Set" /></Row>
                <Row label="RosarioSIS API URL & token"><Pill ok={o.configuration.rosario_configured} okText="Set" /></Row>
                <Row label="Moodle API URL & token"><Pill ok={o.configuration.moodle_configured} okText="Set" /></Row>
                <Row label="DEMO_DATA_ENABLED" detail={o.configuration.demo_data_enabled ? "Test Lab DEMO students are included in syncs" : "Live sources only"}>
                  <Pill ok={o.configuration.demo_data_enabled} okText="true" badText="false" tone="warn" />
                </Row>
                <Row label="Sign-in accounts" detail={`Student linked to record ${o.sign_in.student_account_linked_record || "—"}${o.sign_in.student_record_synchronised ? " (synchronised)" : ""}`}>
                  <span className="text-xs">
                    {(["student", "advisor", "admin"] as const).map((r) => <span key={r} className={`ml-1 ${o.sign_in[r] ? "text-emerald-700" : "text-red-700"}`}>{r} {o.sign_in[r] ? "✓" : "✗"}</span>)}
                  </span>
                </Row>
                <Row label="Session length"><span>{o.configuration.session_hours} h</span></Row>
                <Row label="Experimental ML model" detail={o.ml.error || (o.ml.metrics?.algorithm as string | undefined)}>
                  <Pill ok={o.ml.trained} okText="Trained" badText="Not trained" tone="warn" />
                </Row>
              </ul>
            </Card>
          </div>

          {/* Admin actions */}
          <Card className="mt-6">
            <CardHeader title="Administrator actions" />
            <div className="flex flex-wrap gap-2 px-5 py-4">
              <SyncButton />
              <button className={btnSecondary} onClick={refresh} disabled={checking}>{checking && <Spinner />} Refresh system status</button>
              <Link className={btnSecondary} href="/sync">Open Data Sources & Sync</Link>
              <Link className={btnSecondary} href="/test-lab">Open Test Lab</Link>
              <Link className={btnSecondary} href="/model-performance">Open Model Performance</Link>
              <Link className={btnSecondary} href="/alerts">Open Alerts</Link>
            </div>
          </Card>
        </>
      )}
    </>
  );
}
