import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { setTimeZone } from "./format";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  checking: boolean;
  bootError: string | null;
  login: (studentId: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const accept = useCallback((u: User) => {
    setTimeZone(u.timezone);
    setUser(u);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setChecking(true);
    api<{ user: User }>("/api/auth/me")
      .then((r) => { if (!cancelled) { accept(r.user); setBootError(null); } })
      .catch((e: ApiError) => {
        if (cancelled) return;
        setUser(null);
        setBootError(e.status === 401 ? null : e.message);
      })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, [accept, attempt]);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("lms:unauthorized", onUnauthorized);
    return () => window.removeEventListener("lms:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (studentId: string, password: string) => {
    const r = await api<{ user: User }>("/api/auth/login", { body: { student_id: studentId, password } });
    setBootError(null);
    accept(r.user);
  }, [accept]);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return (
    <AuthContext.Provider value={{ user, checking, bootError, login, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
