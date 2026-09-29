import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useApi } from "../useApi";
import type { NotificationItem } from "../types";
import Icon from "./Icon";

const NAV: { to: string; label: string; icon: string; end?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/courses", label: "My Courses", icon: "courses" },
  { to: "/calendar", label: "Calendar", icon: "calendar" },
  { to: "/assignments", label: "Assignments", icon: "assignment" },
  { to: "/quizzes", label: "Quizzes", icon: "quiz" },
  { to: "/grades", label: "Grades", icon: "grades" },
  { to: "/progress", label: "Progress", icon: "progress" },
  { to: "/activity", label: "Recent Activity", icon: "activity" },
  { to: "/notifications", label: "Notifications", icon: "bell" },
  { to: "/my-coach", label: "My Coach", icon: "coach" },
  { to: "/profile", label: "Profile", icon: "profile" },
];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const notes = useApi<{ notifications: NotificationItem[] }>("/api/notifications");
  const unread = notes.data?.notifications.filter((n) => !n.read).length ?? 0;

  useEffect(() => setOpen(false), [location.pathname]);

  const doLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className={`shell ${open ? "nav-open" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="30" height="30"><rect width="32" height="32" rx="7" fill="#fca311" /><path d="M7 12l9-5 9 5-9 5z" fill="#14213d" /><path d="M11 15v5c0 2 2.5 3.5 5 3.5s5-1.5 5-3.5v-5l-5 2.8z" fill="#fff" /></svg>
          </span>
          <span className="brand-text">
            <strong>My Coach LMS</strong>
            <small>Learning Management</small>
          </span>
          <button className="icon-btn nav-close" onClick={() => setOpen(false)} aria-label="Close menu">
            <Icon name="close" />
          </button>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.to === "/notifications" && unread > 0 && <span className="nav-badge">{unread}</span>}
            </NavLink>
          ))}
          <button className="nav-link nav-logout" onClick={doLogout}>
            <Icon name="logout" />
            <span>Logout</span>
          </button>
        </nav>
        {user && (
          <div className="sidebar-user">
            <span className="avatar" aria-hidden="true">{initials(user.fullname)}</span>
            <span>
              <strong>{user.fullname}</strong>
              <small>Student ID {user.student_id}</small>
            </span>
          </div>
        )}
      </aside>
      <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />
      <div className="main-col">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          <span className="topbar-title">My Coach LMS</span>
          <div className="topbar-right">
            <NavLink to="/notifications" className="icon-btn" aria-label={`Notifications${unread ? ` (${unread} new)` : ""}`}>
              <Icon name="bell" />
              {unread > 0 && <span className="dot" />}
            </NavLink>
            {user && (
              <NavLink to="/profile" className="topbar-user">
                <span className="avatar avatar-sm" aria-hidden="true">{initials(user.fullname)}</span>
                <span className="topbar-name">{user.fullname}</span>
              </NavLink>
            )}
          </div>
        </header>
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
