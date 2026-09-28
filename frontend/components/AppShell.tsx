"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { ApiError, api, clearSession, getStoredUserJson, getToken, homeFor, parseUser, subscribeSession } from "@/lib/api";
import type { SyncRun } from "@/lib/types";
import { Loading, Spinner, StatusBadge, timeAgo } from "./ui";

export const SYNC_EVENT = "mycoach:synced";

const ADMIN_NAV = { href: "/admin", label: "Administration", icon: "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" };

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" },
  { href: "/students", label: "Students", icon: "M16 11c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 3-1.34 3-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5C15 14.17 10.33 13 8 13zm8 0c-.29 0-.62.02-.97.05C16.19 13.89 17 15.02 17 16.5V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" },
  { href: "/alerts", label: "Alerts & Interventions", icon: "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" },
  { href: "/assistant", label: "Advising Assistant", icon: "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z" },
  { href: "/sync", label: "Data Sources & Sync", icon: "M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" },
  { href: "/model-performance", label: "Model Performance", icon: "M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z" },
  { href: "/test-lab", label: "Test Lab", icon: "M7 2v2h1v6.17L3.25 18.5A2 2 0 0 0 5 21.5h14a2 2 0 0 0 1.75-3L16 10.17V4h1V2H7zm3 2h4v6.83l1.63 2.84H8.37L10 10.83V4z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="currentColor" aria-hidden>
      <path d={d} />
    </svg>
  );
}

// ---- Shared sync state -------------------------------------------------------
// Every Sync Data button (header, pages) shares one state, so starting a sync anywhere
// disables all of them and the result banner shows the outcome of that sync.
type SyncOutcome =
  | { kind: "running" }
  | { kind: "done"; run: SyncRun }
  | { kind: "error"; message: string; status: number };

let syncOutcome: SyncOutcome | null = null;
const SYNC_STATE_EVENT = "mycoach:sync-state";

function setSyncOutcome(o: SyncOutcome | null) {
  syncOutcome = o;
  window.dispatchEvent(new Event(SYNC_STATE_EVENT));
}

function subscribeSyncState(cb: () => void) {
  window.addEventListener(SYNC_STATE_EVENT, cb);
  return () => window.removeEventListener(SYNC_STATE_EVENT, cb);
}

function useSyncOutcome() {
  return useSyncExternalStore(subscribeSyncState, () => syncOutcome, () => null);
}

export async function startSync(): Promise<SyncRun | null> {
  if (syncOutcome?.kind === "running") return null;
  setSyncOutcome({ kind: "running" });
  try {
    const run = await api.sync();
    setSyncOutcome({ kind: "done", run });
    window.dispatchEvent(new CustomEvent(SYNC_EVENT, { detail: run }));
    return run;
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0;
    setSyncOutcome({ kind: "error", status, message: e instanceof Error ? e.message : "Synchronisation failed" });
    return null;
  }
}

export function SyncButton({ onDone }: { onDone?: (run: SyncRun) => void }) {
  const outcome = useSyncOutcome();
  const busy = outcome?.kind === "running";

  const run = async () => {
    const result = await startSync();
    if (result) onDone?.(result);
  };

  return (
    <button
      onClick={run}
      disabled={busy}
      aria-busy={busy}
      className="inline-flex items-center gap-2 rounded-lg bg-gold-400 px-4 py-2 text-sm font-semibold text-brand-900 shadow-sm transition hover:bg-gold-500 disabled:cursor-wait disabled:opacity-70"
    >
      {busy ? <Spinner /> : (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden>
          <path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" />
        </svg>
      )}
      {busy ? "Syncing…" : "Sync Data"}
    </button>
  );
}

const SOURCE_NAME: Record<string, string> = { rosario: "RosarioSIS", moodle: "Moodle", demo: "DEMO data" };

/** Result of the most recent Sync Data click: success, partial (names the failed sources) or failure. */
function SyncResultBanner() {
  const outcome = useSyncOutcome();
  if (!outcome) return null;
  const close = (
    <button onClick={() => setSyncOutcome(null)} className="ml-auto text-xs font-medium opacity-70 hover:opacity-100" aria-label="Dismiss">
      Dismiss
    </button>
  );
  if (outcome.kind === "running") {
    return (
      <div data-sync-feedback role="status" className="mb-4 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
        <Spinner /> Synchronising RosarioSIS and Moodle and running the risk rules… this can take up to a minute.
      </div>
    );
  }
  if (outcome.kind === "error") {
    const text = outcome.status === 409 ? "A synchronisation is already running. Wait for it to finish, then try again."
      : outcome.status === 0 ? `${outcome.message} Start the backend (uvicorn main:app --port 8000) and try again.`
      : outcome.message;
    return (
      <div data-sync-feedback role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        <span><b>Sync failed.</b> {text}</span>{close}
      </div>
    );
  }
  const r = outcome.run;
  const entries = Object.entries(r.sources);
  const style = r.status === "completed" ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : r.status === "partial" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-red-200 bg-red-50 text-red-800";
  return (
    <div data-sync-feedback role="status" className={`mb-4 rounded-lg border px-4 py-3 text-sm ${style}`}>
      <div className="flex items-start gap-2">
        <span>
          <b>{r.status === "completed" ? "Sync completed." : r.status === "partial" ? "Partial sync." : "Sync failed."}</b>{" "}
          {r.students_analyzed} student(s) analysed, {r.new_alerts} new alert(s), {r.resolved_alerts} resolved
          {r.joined_students != null && <>, {r.joined_students} RosarioSIS student(s) joined to Moodle</>}.
        </span>
        {close}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        {entries.map(([k, s]) => (
          <li key={k}>
            <span className={`mr-1 inline-block h-2 w-2 rounded-full ${s.status === "ok" ? "bg-emerald-500" : s.status === "not_configured" ? "bg-slate-400" : "bg-red-500"}`} />
            <b>{SOURCE_NAME[k] || k}</b>: {s.status === "ok" ? `synchronised (${s.students} student(s))` : `NOT synchronised — ${s.message}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SyncStatus() {
  const [last, setLast] = useState<SyncRun | null>(null);
  const load = useCallback(() => {
    api.syncRuns(1).then((r) => setLast(r.runs[0] || null)).catch(() => undefined);
  }, []);
  useEffect(() => {
    load();
    const handler = (e: Event) => setLast((e as CustomEvent<SyncRun>).detail);
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [load]);

  if (!last) return <span className="text-xs text-slate-500">Not synchronised yet</span>;
  return (
    <Link href="/sync" className="hidden items-center gap-2 text-xs text-slate-500 hover:text-slate-800 md:flex">
      <span>Last sync {timeAgo(last.finished_at || last.started_at)}</span>
      <StatusBadge status={last.status} />
    </Link>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // undefined = not known yet (server render / hydration), null = signed out
  const token = useSyncExternalStore(subscribeSession, getToken, () => undefined);
  const userJson = useSyncExternalStore(subscribeSession, getStoredUserJson, () => null);
  const user = useMemo(() => parseUser(userJson), [userJson]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (token === null) router.replace("/login");
    else if (user?.role === "student") router.replace(homeFor("student")); // students never use the staff area
    else if (token)
      // The backend decides the role; 401 -> api client redirects to /login
      api.me().then((u) => u.role === "student" && router.replace(homeFor("student"))).catch(() => undefined);
  }, [token, router, user?.role]);

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  if (!token || user?.role === "student") return <Loading label="Checking session…" />;

  const nav = (
    <nav className="flex flex-col gap-1 px-3">
      {(user?.role === "admin" ? [...NAV, ADMIN_NAV] : NAV).map((item) => {
        const active = pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMenuOpen(false)}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
              active ? "bg-white/10 text-white" : "text-brand-100/70 hover:bg-white/5 hover:text-white"
            }`}
          >
            <Icon d={item.icon} />
            {item.label}
            {active && <span className="ml-auto h-5 w-1 rounded-full bg-gold-400" />}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-brand-900 transition-transform lg:translate-x-0 ${
          menuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-3 px-6 py-5">
          <div className="rounded-md bg-gold-400 px-2 py-0.5 text-base font-black text-brand-900">USIU</div>
          <div>
            <p className="text-base font-bold leading-tight text-white">My Coach</p>
            <p className="text-[11px] text-brand-100/60">Risk Detection & Advisory</p>
          </div>
        </div>
        {nav}
        <div className="mt-auto border-t border-white/10 px-6 py-4">
          <p className="truncate text-sm font-medium text-white">{user?.name || "Advisor"}</p>
          <p className="truncate text-xs text-brand-100/60">{user?.email}</p>
          <button onClick={logout} className="mt-3 text-xs font-medium text-gold-400 hover:underline">
            Sign out
          </button>
        </div>
      </aside>
      {menuOpen && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setMenuOpen(false)} />}

      {/* Main */}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-4 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z" /></svg>
          </button>
          <div className="flex-1" />
          <SyncStatus />
          <SyncButton />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <SyncResultBanner />
          {children}
        </main>
      </div>
    </div>
  );
}

/** Re-run `load` whenever a sync completes anywhere in the app. */
export function useOnSync(load: () => void) {
  useEffect(() => {
    window.addEventListener(SYNC_EVENT, load);
    return () => window.removeEventListener(SYNC_EVENT, load);
  }, [load]);
}
