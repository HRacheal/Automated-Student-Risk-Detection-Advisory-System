"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Alert } from "@/lib/types";
import { RISK_META, RiskBadge, SourceBadge, Spinner, StatusBadge, btnSecondary, formatDateTime, inputCls } from "./ui";

export const INTERVENTION_TYPES = [
  "Advising meeting scheduled",
  "Student contacted (email/phone)",
  "Referred to tutoring / learning centre",
  "Referred to counselling / wellness",
  "Referred to Finance / Bursar",
  "Course plan revised",
  "Instructor notified",
  "Registrar consulted (hold / prerequisite)",
  "Other",
];

export function InterventionForm({
  studentId,
  alertId,
  onSaved,
  onCancel,
}: {
  studentId: string;
  alertId?: number | null;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const [actionType, setActionType] = useState(INTERVENTION_TYPES[0]);
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("planned");
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createIntervention({
        student_id: studentId,
        alert_id: alertId ?? null,
        action_type: actionType,
        notes: notes || undefined,
        status,
        follow_up_date: followUp || undefined,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs font-medium text-slate-600 sm:col-span-2">
          Action
          <select className={`${inputCls} mt-1`} value={actionType} onChange={(e) => setActionType(e.target.value)}>
            {INTERVENTION_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Status
          <select className={`${inputCls} mt-1`} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="planned">Planned</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </label>
      </div>
      <label className="block text-xs font-medium text-slate-600">
        Notes
        <textarea className={`${inputCls} mt-1`} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What was agreed with the student?" />
      </label>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-slate-600">
          Follow-up date
          <input type="date" className={`${inputCls} mt-1`} value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
        </label>
        <div className="ml-auto flex gap-2">
          {onCancel && <button type="button" className={btnSecondary} onClick={onCancel}>Cancel</button>}
          <button type="submit" disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-brand-900 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
            {busy && <Spinner />} Log intervention
          </button>
        </div>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  );
}

export default function AlertCard({ alert, onChanged, showStudent = false }: { alert: Alert; onChanged: () => void; showStudent?: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = alert.status === "active" || alert.status === "acknowledged";

  const setStatus = async (status: "active" | "acknowledged" | "resolved") => {
    setBusy(status);
    setError(null);
    try {
      await api.updateAlert(alert.id, status);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={`rounded-xl border border-slate-200 border-l-4 bg-white p-5 shadow-sm ${RISK_META[alert.severity].ring} ${open ? "" : "opacity-80"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <RiskBadge level={alert.severity} />
        <h3 className="text-base font-semibold text-slate-900">{alert.title}</h3>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Rule-based</span>
        <span className="ml-auto"><StatusBadge status={alert.status} /></span>
      </div>
      {showStudent && (
        <p className="mt-1 text-sm">
          <Link href={`/students/${encodeURIComponent(alert.student_id)}`} className="font-medium text-brand-700 hover:underline">
            {alert.student_name || alert.student_id}
          </Link>{" "}
          <span className="text-xs text-slate-500">({alert.student_id})</span>
        </p>
      )}
      <p className="mt-2 text-sm text-slate-700">{alert.description}</p>

      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Evidence</p>
          <ul className="mt-1.5 space-y-1">
            {alert.evidence.map((e, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-700">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                {e}
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
            Source: {alert.data_sources.map((s) => <SourceBadge key={s} source={s} />)}
          </div>
        </div>
        <div className="rounded-lg bg-brand-100/60 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-800">Recommended intervention</p>
          <p className="mt-1 text-sm text-slate-800">{alert.recommended_intervention}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span>Detected {formatDateTime(alert.detected_at)}</span>
        <span>· Last seen {formatDateTime(alert.last_seen_at)}</span>
        {alert.resolved_at && <span>· Resolved {formatDateTime(alert.resolved_at)}</span>}
        <div className="ml-auto flex flex-wrap gap-2">
          {alert.status === "active" && (
            <button className={btnSecondary} disabled={!!busy} onClick={() => setStatus("acknowledged")}>
              {busy === "acknowledged" && <Spinner />} Acknowledge
            </button>
          )}
          {open && (
            <>
              <button className={btnSecondary} onClick={() => setShowForm((v) => !v)}>Log intervention</button>
              <button className={btnSecondary} disabled={!!busy} onClick={() => setStatus("resolved")}>
                {busy === "resolved" && <Spinner />} Mark resolved
              </button>
            </>
          )}
          {!open && (
            <button className={btnSecondary} disabled={!!busy} onClick={() => setStatus("active")}>
              {busy === "active" && <Spinner />} Reopen
            </button>
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {showForm && (
        <div className="mt-3">
          <InterventionForm
            studentId={alert.student_id}
            alertId={alert.id}
            onCancel={() => setShowForm(false)}
            onSaved={() => {
              setShowForm(false);
              onChanged();
            }}
          />
        </div>
      )}
    </div>
  );
}
