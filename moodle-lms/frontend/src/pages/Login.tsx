import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import Icon from "../components/Icon";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || "/";
  const [studentId, setStudentId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(studentId.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-panel">
        <div className="login-brand">
          <svg viewBox="0 0 32 32" width="44" height="44" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#fca311" /><path d="M7 12l9-5 9 5-9 5z" fill="#14213d" /><path d="M11 15v5c0 2 2.5 3.5 5 3.5s5-1.5 5-3.5v-5l-5 2.8z" fill="#fff" /></svg>
          <div>
            <h1>My Coach LMS</h1>
            <p>Your courses, assignments, quizzes and grades - from Moodle.</p>
          </div>
        </div>
        <form onSubmit={submit} className="login-form" noValidate>
          <label htmlFor="sid">Student ID</label>
          <input id="sid" name="username" inputMode="numeric" autoComplete="username" required value={studentId}
                 onChange={(e) => setStudentId(e.target.value)} placeholder="e.g. 690025" autoFocus />
          <label htmlFor="pw">Password</label>
          <input id="pw" name="password" type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
          {error && <div className="form-error" role="alert"><Icon name="alert" size={16} /> {error}</div>}
          <button className="btn btn-primary btn-block" disabled={busy || !studentId || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="muted small login-note">
            Signs you in with your Moodle account. Your password is checked by Moodle and is never stored by this app.
          </p>
        </form>
      </div>
      <div className="login-art" aria-hidden="true">
        <div>
          <h2>Learn. Submit. Track your progress.</h2>
          <p>Everything here comes live from Moodle. Academic advising lives in My Coach.</p>
        </div>
      </div>
    </div>
  );
}
