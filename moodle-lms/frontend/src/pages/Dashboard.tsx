import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import Icon from "../components/Icon";
import { Card, ErrorState, PageHeader, ProgressBar, Skeleton } from "../components/ui";
import { ActivityList, CoachCard, CourseTile, DeadlineList, markRead, NotificationList } from "../components/widgets";
import { dateOnly } from "../format";
import type { Dashboard } from "../types";
import { useApi } from "../useApi";

export default function DashboardPage() {
  const { user } = useAuth();
  const dash = useApi<Dashboard>("/api/dashboard");
  const d = dash.data;

  return (
    <div className="page">
      <PageHeader
        title={<>Welcome, {user?.fullname}</>}
        subtitle={<>Student ID: <strong>{user?.student_id}</strong> · {dateOnly(Date.now() / 1000)}</>}
        actions={<button className="btn btn-secondary btn-sm" onClick={dash.reload} disabled={dash.loading}>
          <Icon name="refresh" size={14} /> Refresh</button>}
      />

      {dash.error ? <ErrorState error={dash.error} onRetry={dash.reload} /> : (
        <>
          <div className="stats">
            <Stat label="Enrolled courses" value={d ? d.courses.length : null} icon="courses" to="/courses" />
            <Stat label="Due in 3 weeks" value={d ? d.upcoming.length : null} icon="clock" to="/assignments" />
            <Stat label="Overdue" value={d ? d.overdue.length : null} icon="alert" to="/assignments?filter=overdue"
                  tone={d && d.overdue.length ? "danger" : undefined} />
            <Stat label="Activities completed" value={d ? `${d.progress.completed}/${d.progress.tracked}` : null}
                  icon="progress" to="/progress" />
          </div>

          <div className="dash-grid">
            <div className="dash-main">
              <Card title="My Courses" action={<Link to="/courses" className="link-sm">View all</Link>}>
                {!d ? <Skeleton rows={3} /> : d.courses.length === 0
                  ? <p className="muted">You are not enrolled in any Moodle course.</p>
                  : <div className="course-grid">{d.courses.map((c) => <CourseTile key={c.id} course={c} />)}</div>}
              </Card>

              <Card title="Upcoming" action={<Link to="/calendar" className="link-sm">Calendar</Link>}>
                {!d ? <Skeleton rows={4} /> : (
                  <>
                    {d.overdue.length > 0 && (
                      <>
                        <h3 className="subhead text-danger">Overdue - late submission still accepted</h3>
                        <DeadlineList items={d.overdue} />
                        <h3 className="subhead">Coming up</h3>
                      </>
                    )}
                    <DeadlineList items={d.upcoming} />
                  </>
                )}
              </Card>

              <Card title="Recent Activity" action={<Link to="/activity" className="link-sm">View all</Link>}>
                {!d ? <Skeleton rows={4} /> : <ActivityList items={d.recent_activity.slice(0, 8)} />}
              </Card>
            </div>

            <aside className="dash-side">
              <CoachCard compact />
              <Card title="Progress">
                {!d ? <Skeleton rows={2} /> : (
                  <>
                    <ProgressBar value={d.progress.average_course_progress} label="Average course progress" />
                    <p className="small muted">Average of Moodle's course progress across your {d.courses.length} courses.
                      {" "}{d.progress.completed} of {d.progress.tracked} tracked activities are complete.</p>
                    <ul className="mini-progress">
                      {d.courses.map((c) => (
                        <li key={c.id}><Link to={`/courses/${c.id}`}>{c.code}</Link><ProgressBar value={c.progress} size="sm" label={c.code} /></li>
                      ))}
                    </ul>
                  </>
                )}
              </Card>
              <Card title="Notifications" action={<Link to="/notifications" className="link-sm">View all</Link>}>
                {!d ? <Skeleton rows={3} /> : <NotificationList items={d.notifications.slice(0, 5)} onRead={markRead} />}
              </Card>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, icon, to, tone }: { label: string; value: number | string | null; icon: string; to: string; tone?: string }) {
  return (
    <Link to={to} className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <span className="stat-icon"><Icon name={icon} /></span>
      <span>
        <span className="stat-value">{value ?? "…"}</span>
        <span className="stat-label">{label}</span>
      </span>
    </Link>
  );
}
