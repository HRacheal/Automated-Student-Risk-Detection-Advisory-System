import { Link } from "react-router-dom";
import { Card, Field, Loaded, PageHeader, Skeleton } from "../components/ui";
import { dateTime } from "../format";
import type { Profile } from "../types";
import { useApi } from "../useApi";

export default function ProfilePage() {
  const state = useApi<Profile>("/api/profile");
  return (
    <div className="page">
      <PageHeader title="Profile" subtitle="Your student account" />
      <Loaded state={state} skeleton={<Skeleton rows={5} />}>
        {(p) => (
          <div className="detail-grid">
            <div className="detail-main">
              <Card title="Student">
                <dl className="fields">
                  <Field label="Name">{p.fullname}</Field>
                  <Field label="Student ID">{p.student_id}</Field>
                  <Field label="Major / program">{p.program ?? <span className="muted">Not available</span>}</Field>
                  <Field label="Moodle username">{p.username}</Field>
                  <Field label="Email">{p.email ?? "—"}</Field>
                  {p.department && <Field label="Department">{p.department}</Field>}
                </dl>
              </Card>
              <Card title={`Enrolled courses (${p.courses.length})`}>
                <ul className="list compact">
                  {p.courses.map((c) => (
                    <li key={c.id}><Link to={`/courses/${c.id}`} className="list-row">
                      <span className="list-main"><strong>{c.code}</strong><span className="small">{c.title}{c.term ? ` · ${c.term}` : ""}</span></span>
                    </Link></li>
                  ))}
                </ul>
              </Card>
            </div>
            <aside className="detail-side">
              <Card title="Moodle access">
                <dl className="fields">
                  <Field label="First access">{dateTime(p.first_access)}</Field>
                  <Field label="Last access">{dateTime(p.last_access)}</Field>
                </dl>
                <p className="muted small">Only your own account details are shown. Program information comes from My Coach.</p>
              </Card>
            </aside>
          </div>
        )}
      </Loaded>
    </div>
  );
}
