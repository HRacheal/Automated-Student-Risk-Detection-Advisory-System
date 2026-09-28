"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, clearSession, getStoredUserJson, getToken, homeFor, parseUser, subscribeSession } from "@/lib/api";
import type { MyRecord, User } from "@/lib/types";
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
  btnSecondary,
  formatDate,
  formatDateTime,
} from "@/components/ui";

// The student portal only ever shows the signed-in student's OWN record. Nothing here
// sends a student id: the backend takes it from the signed session token.
export default function StudentPortal() {
  const router = useRouter();
  const token = useSyncExternalStore(subscribeSession, getToken, () => undefined);
  const userJson = useSyncExternalStore(subscribeSession, getStoredUserJson, () => null);
  const storedUser = useMemo(() => parseUser(userJson), [userJson]);
  const [me, setMe] = useState<User | null>(null);
  const [record, setRecord] = useState<MyRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Verify the session with the backend (the role in localStorage is only a UI hint).
  useEffect(() => {
    if (token === undefined) return;
    if (token === null) {
      router.replace("/login?as=student");
      return;
    }
    let cancelled = false;
    api.me()
      .then((u) => {
        if (cancelled) return;
        if (u.role !== "student") router.replace(homeFor(u.role));
        else setMe(u);
      })
      .catch(() => undefined); // 401 -> api client redirects to /login
    return () => {
      cancelled = true;
    };
  }, [token, router]);

  const fetchRecord = useCallback(() => {
    api.myRecord()
      .then((r) => { setRecord(r); setError(null); setNotice(null); })
      .catch((e) => {
        // 404 = not synchronised yet, 409 = account not linked: expected states, not failures.
        if (e instanceof ApiError && (e.status === 404 || e.status === 409)) setNotice(e.message);
        else setError(e instanceof Error ? e.message : "Could not load your record");
      })
      .finally(() => setLoading(false));
  }, []);
  const load = () => {
    setLoading(true);
    fetchRecord();
  };

  useEffect(() => {
    if (me) fetchRecord();
  }, [me, fetchRecord]);

  const logout = () => {
    clearSession();
    router.replace("/login?as=student");
  };

  if (!token || !me) return <Loading label="Checking session…" />;

  const s = record?.student;
  const name = s?.full_name || me.name || storedUser?.name || "Student";
  const enrolled = s?.current_courses.filter((c) => c.status === "enrolled") ?? [];
  const dropped = s?.current_courses.filter((c) => c.status === "dropped") ?? [];
  const units = enrolled.reduce((n, c) => n + (c.units || 0), 0);
  const missed = s?.lms.assignments.filter((a) => a.status === "missed") ?? [];
  const quizzes = s?.lms.quizzes.filter((q) => q.percent !== null) ?? [];
  const quizAvg = quizzes.length ? quizzes.reduce((n, q) => n + (q.percent || 0), 0) / quizzes.length : null;

  return (
    <div className="min-h-screen">
      <header className="bg-brand-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-4 sm:px-6">
          <div className="rounded-md bg-gold-400 px-2 py-0.5 text-base font-black text-brand-900">USIU</div>
          <div className="flex-1">
            <p className="text-base font-bold leading-tight">My Coach</p>
            <p className="text-[11px] text-brand-100/60">Student portal</p>
          </div>
          <div className="text-right">
            <p className="text-sm font-medium">{me.name}</p>
            <button onClick={logout} className="text-xs font-medium text-gold-400 hover:underline">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Welcome, {name.split(" ")[0]}</h1>
            <p className="mt-1 text-sm text-slate-500">
              Your academic progress, indicators and recommended next steps
              {record && <> · last updated {formatDateTime(record.last_synced_at)}</>}
            </p>
          </div>
          <button className={btnSecondary} onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>

        <ErrorBanner message={error} />
        {notice && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" role="status">
            {notice} Please check back after your advisor runs the next data synchronisation.
          </div>
        )}

        {loading && !record ? (
          <Loading label="Loading your record…" />
        ) : s && record ? (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              {/* Overview */}
              <Card className={`border-l-4 ${RISK_META[record.risk_level]?.ring || ""}`}>
                <div className="grid gap-4 p-5 sm:grid-cols-4">
                  <Stat label="Overall status"><RiskBadge level={record.risk_level} size="lg" /></Stat>
                  <Stat label="Cumulative GPA">{s.cumulative_gpa != null ? s.cumulative_gpa.toFixed(2) : "—"}</Stat>
                  <Stat label="Units completed">{s.completed_units ?? "—"}</Stat>
                  <Stat label="Class standing">{s.class_standing || "—"}</Stat>
                </div>
              </Card>

              {/* Indicators + recommendations */}
              <Card>
                <CardHeader
                  title="Your indicators & recommended next steps"
                  subtitle="Rule-based checks on your RosarioSIS and Moodle data"
                />
                {record.indicators.length === 0 ? (
                  <EmptyState title="No active concerns were detected. Keep it up!" />
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {record.indicators.map((a, i) => (
                      <li key={`${a.title}-${i}`} className={`border-l-4 px-5 py-4 ${RISK_META[a.severity]?.ring || ""}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-slate-900">{a.title}</p>
                          <RiskBadge level={a.severity} />
                          <span className="text-xs text-slate-400">since {formatDate(a.detected_at)}</span>
                        </div>
                        <p className="mt-1 text-sm text-slate-700">{a.description}</p>
                        {a.evidence.length > 0 && (
                          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-500">
                            {a.evidence.slice(0, 5).map((e) => <li key={e}>{e}</li>)}
                          </ul>
                        )}
                        {a.recommended_action && (
                          <p className="mt-2 rounded-lg bg-brand-100/40 px-3 py-2 text-sm text-brand-900">
                            <span className="font-semibold">Recommended: </span>{a.recommended_action}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              {/* Courses */}
              <Card>
                <CardHeader
                  title={`Current courses${s.current_term ? ` · ${s.current_term}` : ""}`}
                  subtitle={`${enrolled.length} active course(s), ${units} units`}
                />
                {s.current_courses.length === 0 ? (
                  <EmptyState title="No course registrations found for the current term." />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-5 py-2.5 font-medium">Course</th>
                          <th className="px-3 py-2.5 font-medium">Title</th>
                          <th className="px-3 py-2.5 text-right font-medium">Units</th>
                          <th className="px-5 py-2.5 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {[...enrolled, ...dropped].map((c) => (
                          <tr key={`${c.code}-${c.status}`}>
                            <td className="px-5 py-2.5 font-medium text-slate-900">{c.code}</td>
                            <td className="px-3 py-2.5 text-slate-600">{c.title || "—"}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums">{c.units ?? "—"}</td>
                            <td className="px-5 py-2.5 capitalize text-slate-600">{c.status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              {/* GPA / progress */}
              <Card>
                <CardHeader title="GPA & progress" subtitle="Term GPA history from RosarioSIS" />
                {s.term_gpas.length === 0 ? (
                  <EmptyState title="No graded terms on record yet." />
                ) : (
                  <div className="flex flex-wrap gap-3 p-5">
                    {s.term_gpas.map((t) => (
                      <div key={t.term} className="min-w-28 rounded-lg border border-slate-200 px-3 py-2">
                        <p className="text-xs text-slate-500">{t.term}</p>
                        <p className="text-lg font-semibold tabular-nums text-slate-900">{t.gpa.toFixed(2)}</p>
                        <p className="text-[11px] text-slate-400">{t.credits} credits</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            <div className="space-y-6">
              {/* Profile */}
              <Card>
                <CardHeader title="My profile" />
                <dl className="space-y-2 px-5 py-4 text-sm">
                  <Row label="Name">{s.full_name}</Row>
                  <Row label="Student ID">{s.student_id}</Row>
                  <Row label="Major">{s.major_field_available ? s.declared_major || "—" : "Not available"}</Row>
                  <Row label="School">{s.school || "—"}</Row>
                  <Row label="Enrollment">{s.enrollment_status || "—"}</Row>
                  <Row label="Sources">
                    <span className="flex flex-wrap justify-end gap-1">{s.sources.map((src) => <SourceBadge key={src} source={src} />)}</span>
                  </Row>
                </dl>
              </Card>

              {/* Moodle */}
              <Card>
                <CardHeader title="Moodle activity" />
                {!s.lms.available ? (
                  <p className="px-5 py-4 text-sm text-slate-500">Moodle data is not available for your account.</p>
                ) : (
                  <dl className="space-y-2 px-5 py-4 text-sm">
                    <Row label="Last access">{s.lms.last_access ? formatDateTime(s.lms.last_access) : "Never"}</Row>
                    <Row label="Assignments">{s.lms.assignments.length} tracked, {missed.length} missed</Row>
                    <Row label="Quiz average">{quizAvg != null ? `${quizAvg.toFixed(0)}%` : "—"}</Row>
                  </dl>
                )}
              </Card>

              {/* Chatbot */}
              <Card className="overflow-hidden">
                <CardHeader title="Ask My Coach" subtitle="Answers use only your own record" />
                <ChatPanel mode="self" studentName={s.full_name} height="h-80" />
              </Card>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-1 text-xl font-semibold text-slate-900">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right text-slate-900">{children}</dd>
    </div>
  );
}
