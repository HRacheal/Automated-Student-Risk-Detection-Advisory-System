import type {
  AdminOverview,
  Alert,
  AlertEvent,
  DashboardSummary,
  IntegrationStatus,
  Intervention,
  MLStatus,
  ModelPerformanceReport,
  MyRecord,
  Role,
  StudentDetail,
  StudentSummary,
  SyncRun,
  SyncStatus,
  TestLab,
  User,
} from "./types";

// FastAPI base URL. Set NEXT_PUBLIC_API_URL in frontend/.env.local for other hosts.
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const TOKEN_KEY = "mycoach_token";
const USER_KEY = "mycoach_user";

/** Landing page for each role after sign-in. */
export function homeFor(role: string | undefined | null): string {
  if (role === "student") return "/student";
  if (role === "admin") return "/admin";
  return "/dashboard";
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Raw JSON of the signed-in user (a string, so it is a stable useSyncExternalStore snapshot). */
export function getStoredUserJson(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(USER_KEY);
  } catch {
    return null;
  }
}

export function parseUser(raw: string | null): User | null {
  try {
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

const SESSION_EVENT = "mycoach:session";

/** Subscribe to sign-in / sign-out in this tab and in other tabs. */
export function subscribeSession(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(SESSION_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(SESSION_EVENT, callback);
  };
}

export function saveSession(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    window.dispatchEvent(new Event(SESSION_EVENT));
  } catch {
    /* ignore */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_BASE_URL}. Is the FastAPI server running?`);
  }
  if (res.status === 401 && path !== "/api/auth/login") {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      // Hard navigation from a non-React helper; clears all client state after the session ended.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login?expired=1";
    }
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const qs = (params: Record<string, string | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) p.set(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // The selected role is only a hint; the backend decides the role from the credentials.
  login: (email: string, password: string, role: Role) =>
    request<{ token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    }),
  roles: () => request<Record<Role, boolean>>("/api/auth/roles"),
  me: () => request<User>("/api/auth/me"),

  dashboard: () => request<DashboardSummary>("/api/dashboard/summary"),
  students: (params: { q?: string; risk?: string; source?: string; anomaly_type?: string } = {}) =>
    request<{ students: StudentSummary[]; count: number }>(`/api/students${qs(params)}`),
  student: (id: string) => request<StudentDetail>(`/api/students/${encodeURIComponent(id)}`),

  alerts: (params: { status?: string; severity?: string; anomaly_type?: string; student_id?: string; q?: string } = {}) =>
    request<{ alerts: Alert[]; count: number; types: { type: string; title: string }[] }>(`/api/alerts${qs(params)}`),
  updateAlert: (id: number, status: "active" | "acknowledged" | "resolved", note?: string) =>
    request<Alert>(`/api/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ status, note }) }),
  alertEvents: (id: number) => request<{ events: AlertEvent[] }>(`/api/alerts/${id}/events`),

  interventions: (params: { student_id?: string; status?: string } = {}) =>
    request<{ interventions: Intervention[] }>(`/api/interventions${qs(params)}`),
  createIntervention: (body: {
    student_id: string;
    alert_id?: number | null;
    action_type: string;
    notes?: string;
    status?: string;
    follow_up_date?: string;
  }) => request<Intervention>("/api/interventions", { method: "POST", body: JSON.stringify(body) }),
  updateIntervention: (id: number, body: { status?: string; notes?: string }) =>
    request<Intervention>(`/api/interventions/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  sync: () => request<SyncRun>("/api/sync", { method: "POST" }),
  syncRuns: (limit = 20) => request<{ runs: SyncRun[] }>(`/api/sync/runs?limit=${limit}`),
  syncStatus: () => request<SyncStatus>("/api/sync/status"),
  health: () => request<{ status: string; database: string; demo_data_enabled: boolean }>("/api/health"),
  integrations: () => request<IntegrationStatus>("/api/integrations/status"),

  testLab: () => request<TestLab>("/api/test-lab"),
  toggleScenario: (student_id: string, scenario_key: string, enabled: boolean) =>
    request<{ ok: boolean }>("/api/test-lab/scenarios", {
      method: "PUT",
      body: JSON.stringify({ student_id, scenario_key, enabled }),
    }),
  resetScenarios: () => request<{ ok: boolean }>("/api/test-lab/reset", { method: "POST" }),

  mlStatus: () => request<MLStatus>("/api/ml/status"),
  // Student self-service (always the signed-in student's own record)
  myRecord: () => request<MyRecord>("/api/student/me"),
  myChat: (message: string) =>
    request<{ response: string; student_id: string | null; intent: string | null }>("/api/student/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  adminOverview: () => request<AdminOverview>("/api/admin/overview"),
  modelPerformance: () => request<ModelPerformanceReport>("/api/model-performance"),

  chat: (message: string, student_id?: string | null) =>
    request<{ response: string; student_id: string | null; intent: string | null }>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, student_id: student_id || null }),
    }),
};
