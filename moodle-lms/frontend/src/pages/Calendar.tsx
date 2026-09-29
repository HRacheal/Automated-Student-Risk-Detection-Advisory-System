import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { Card, EmptyState, Loaded, PageHeader, Skeleton } from "../components/ui";
import { courseColor } from "../components/widgets";
import { getTimeZone, timeOnly, zonedParts } from "../format";
import type { CalendarEvent } from "../types";
import { useApi } from "../useApi";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function thisMonth() {
  const p = zonedParts(Date.now() / 1000);
  return `${p.year}-${String(p.month).padStart(2, "0")}`;
}

function shift(month: string, delta: number) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default function CalendarPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") || "") ? params.get("month")! : thisMonth();
  const state = useApi<{ month: string; events: CalendarEvent[] }>(`/api/calendar?month=${month}`);
  const [year, mon] = month.split("-").map(Number);
  const label = new Date(Date.UTC(year, mon - 1, 15)).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  const today = zonedParts(Date.now() / 1000);

  const byDay = useMemo(() => {
    const m = new Map<number, CalendarEvent[]>();
    for (const e of state.data?.events ?? []) {
      const p = zonedParts(e.start);
      if (p.year === year && p.month === mon) m.set(p.day, [...(m.get(p.day) ?? []), e]);
    }
    return m;
  }, [state.data, year, mon]);

  const cells = useMemo(() => {
    const first = new Date(Date.UTC(year, mon - 1, 1)).getUTCDay(); // 0 = Sunday
    const lead = (first + 6) % 7;
    const days = new Date(Date.UTC(year, mon, 0)).getUTCDate();
    return [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  }, [year, mon]);

  const setMonth = (m: string) => setParams(m === thisMonth() ? {} : { month: m }, { replace: true });

  return (
    <div className="page">
      <PageHeader title="Calendar" subtitle={`Deadlines and course events from Moodle · times in ${getTimeZone()}`}
        actions={
          <div className="cal-nav">
            <button className="icon-btn" onClick={() => setMonth(shift(month, -1))} aria-label="Previous month"><Icon name="chevronLeft" /></button>
            <strong className="cal-label">{label}</strong>
            <button className="icon-btn" onClick={() => setMonth(shift(month, 1))} aria-label="Next month"><Icon name="chevronRight" /></button>
            <button className="btn btn-secondary btn-sm" onClick={() => setMonth(thisMonth())}>Today</button>
          </div>
        } />
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => (
          <div className="cal-layout">
            <Card pad={false} className="cal-card">
              <div className="cal-grid" role="grid" aria-label={label}>
                {WEEKDAYS.map((w) => <div key={w} className="cal-weekday" role="columnheader">{w}</div>)}
                {cells.map((day, i) => {
                  const isToday = day && today.year === year && today.month === mon && today.day === day;
                  const events = day ? byDay.get(day) ?? [] : [];
                  return (
                    <div key={i} className={`cal-cell ${day ? "" : "empty"} ${isToday ? "today" : ""}`} role="gridcell">
                      {day && <span className="cal-day">{day}</span>}
                      {events.slice(0, 3).map((e) => (
                        <CalChip key={e.id} e={e} />
                      ))}
                      {events.length > 3 && <span className="cal-more">+{events.length - 3} more</span>}
                    </div>
                  );
                })}
              </div>
            </Card>
            <Card title="Agenda" className="cal-agenda">
              {d.events.length === 0 ? <EmptyState title="No events this month." icon="calendar" /> : (
                <ol className="agenda">
                  {[...byDay.entries()].sort((a, b) => a[0] - b[0]).map(([day, events]) => (
                    <li key={day}>
                      <h3>{new Date(Date.UTC(year, mon - 1, day)).toLocaleDateString("en-US", { weekday: "short", month: "long", day: "numeric", timeZone: "UTC" })}</h3>
                      <ul>
                        {events.map((e) => (
                          <li key={e.id} className="agenda-item">
                            <span className="agenda-bar" style={{ background: courseColor(e.course_code) }} />
                            <span className="list-main">
                              {e.link ? <Link to={e.link} className="strong-link">{e.course_code} {e.name}</Link> : <strong>{e.course_code} {e.name}</strong>}
                              <span className="muted small">{e.event_type === "due" ? "Due" : e.event_type === "close" ? "Closes" : e.event_type === "open" ? "Opens" : "At"} {timeOnly(e.start)}</span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        )}
      </Loaded>
    </div>
  );
}

function CalChip({ e }: { e: CalendarEvent }) {
  const text = `${timeOnly(e.start)} ${e.course_code ?? ""} ${e.name}`;
  const style = { borderLeftColor: courseColor(e.course_code) };
  return e.link
    ? <Link to={e.link} className="cal-chip" style={style} title={text}>{text}</Link>
    : <span className="cal-chip" style={style} title={text}>{text}</span>;
}
