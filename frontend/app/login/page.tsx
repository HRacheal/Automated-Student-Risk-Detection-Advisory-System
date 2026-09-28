"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getStoredUserJson, getToken, homeFor, parseUser, saveSession } from "@/lib/api";
import type { Role } from "@/lib/types";
import { Spinner, btnPrimary, inputCls } from "@/components/ui";

const ROLES: { role: Role; label: string; heading: string; hint: string; icon: string }[] = [
  {
    role: "student", label: "Student", heading: "Student Sign In",
    hint: "View your own academic progress, indicators and recommended next steps.",
    icon: "M12 3L1 9l11 6 9-4.91V17h2V9L12 3zm-6.82 9.17v4L12 20l6.82-3.83v-4L12 16l-6.82-3.83z",
  },
  {
    role: "advisor", label: "Advisor", heading: "Advisor Sign In",
    hint: "Use your advising account to access the risk dashboard.",
    icon: "M16 11c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 3-1.34 3-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5C15 14.17 10.33 13 8 13zm8 0c-.29 0-.62.02-.97.05C16.19 13.89 17 15.02 17 16.5V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z",
  },
  {
    role: "admin", label: "Admin", heading: "Admin Sign In",
    hint: "System administration: configuration status, data sources and synchronisation.",
    icon: "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z",
  },
];

export default function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = use(searchParams);
  const expired = Boolean(params.expired);
  const initialRole = (["student", "advisor", "admin"] as const).find((r) => r === params.as) || "advisor";
  const router = useRouter();
  const [role, setRole] = useState<Role>(initialRole);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace(homeFor(parseUser(getStoredUserJson())?.role));
  }, [router]);

  const current = ROLES.find((r) => r.role === role)!;

  const selectRole = (r: Role) => {
    setRole(r);
    setError("");
    setPassword("");
  };

  const handleLogin = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { token, user } = await api.login(email.trim(), password, role);
      saveSession(token, user);
      router.replace(homeFor(user.role)); // role decided by the backend, not by the selected tab
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-brand-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-gold-400 px-3 py-1 text-xl font-black text-brand-900">USIU</div>
          <div>
            <p className="text-lg font-bold leading-tight">My Coach</p>
            <p className="text-xs text-brand-100/70">Academic Advising Platform</p>
          </div>
        </div>
        <div className="max-w-md">
          <h1 className="text-3xl font-bold leading-tight">
            Detect academic risk early.
            <br />
            <span className="text-gold-400">Intervene with evidence.</span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-brand-100/80">
            My Coach combines RosarioSIS academic records and Moodle learning activity, applies transparent advising
            rules, and shows advisors exactly why a student was flagged and what to do next.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100/90">
            {[
              "Course-major mismatch, prerequisite and withdrawal checks",
              "GPA trends, grades, holds and tuition signals",
              "Missed assignments, quiz scores and LMS engagement",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-brand-100/50">United States International University – Africa</p>
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-700/40 blur-3xl" />
      </div>

      {/* Sign-in */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center gap-3">
            <div className="rounded-lg bg-gold-400 px-3 py-1 text-xl font-black text-brand-900 lg:hidden">USIU</div>
            <div>
              <p className="text-lg font-bold text-slate-900">My Coach</p>
              <p className="text-xs text-slate-500">Academic Advising Platform</p>
            </div>
          </div>

          {/* Role selector */}
          <div role="tablist" aria-label="Sign in as" className="grid grid-cols-3 gap-2 rounded-xl bg-slate-100 p-1.5">
            {ROLES.map((r) => {
              const active = r.role === role;
              return (
                <button
                  key={r.role}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => selectRole(r.role)}
                  className={`flex flex-col items-center gap-1 rounded-lg px-2 py-2.5 text-xs font-semibold transition ${
                    active ? "bg-white text-brand-900 shadow-sm ring-1 ring-slate-200" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  <svg viewBox="0 0 24 24" className={`h-5 w-5 ${active ? "text-brand-700" : "text-slate-400"}`} fill="currentColor" aria-hidden>
                    <path d={r.icon} />
                  </svg>
                  Login as {r.label}
                </button>
              );
            })}
          </div>

          <h2 className="mt-8 text-2xl font-bold text-slate-900">{current.heading}</h2>
          <p className="mt-1 text-sm text-slate-500">{current.hint}</p>

          {expired && !error && (
            <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Your session has expired. Please sign in again.
            </div>
          )}
          {error && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="mt-6 space-y-4" aria-label={current.heading}>
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
                {current.label} email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={`${role}@usiu.ac.ke`}
                required
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className={inputCls}
              />
            </div>
            <button type="submit" disabled={loading} className={`${btnPrimary} w-full py-2.5`}>
              {loading && <Spinner />}
              {loading ? "Signing in…" : `Sign in as ${current.label}`}
            </button>
          </form>
          <p className="mt-6 text-xs leading-relaxed text-slate-400">
            Accounts are configured on the server ({role.toUpperCase()}_EMAIL / {role.toUpperCase()}_PASSWORD in backend/.env).
          </p>
        </div>
      </div>
    </div>
  );
}
