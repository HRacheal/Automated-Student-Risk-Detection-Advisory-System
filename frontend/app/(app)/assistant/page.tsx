"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { StudentSummary } from "@/lib/types";
import ChatPanel from "@/components/ChatPanel";
import { Card, CardHeader, PageHeader, RISK_META, inputCls } from "@/components/ui";

export default function AssistantPage() {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    api.students().then((r) => setStudents(r.students)).catch(() => undefined);
  }, []);

  const current = students.find((s) => s.student_id === selected);

  return (
    <>
      <PageHeader
        title="Advising Assistant"
        subtitle="A rule-based assistant (no external AI service). Every answer is built from the synchronised student record and stored alerts."
      />
      <Card>
        <CardHeader
          title={current ? `Talking about ${current.full_name}` : "General questions"}
          subtitle={current ? `${RISK_META[current.risk_level].icon} ${current.risk_level} risk · ${current.open_alerts} open alert(s)` : "Select a student for student-specific answers"}
          action={
            <select className={`${inputCls} w-72`} value={selected} onChange={(e) => setSelected(e.target.value)} aria-label="Student">
              <option value="">— No student selected —</option>
              {students.map((s) => (
                <option key={s.student_id} value={s.student_id}>
                  {RISK_META[s.risk_level].icon} {s.full_name} ({s.student_id})
                </option>
              ))}
            </select>
          }
        />
        <ChatPanel key={selected || "general"} studentId={selected || null} studentName={current?.full_name} height="h-[30rem]" />
      </Card>
    </>
  );
}
