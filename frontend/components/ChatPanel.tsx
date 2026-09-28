"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import Markdown from "./Markdown";
import { Spinner } from "./ui";

interface Message {
  sender: "user" | "bot";
  text: string;
}

const STUDENT_QUESTIONS = [
  "What anomalies were detected for this student?",
  "Why was this student flagged?",
  "What courses is this student currently taking?",
  "What intervention is recommended?",
  "What should the student discuss with their advisor?",
  "Show the GPA trend",
  "How is the student doing in Moodle?",
];
const GENERAL_QUESTIONS = ["Which students are high risk?", "How many alerts are open?"];
const SELF_QUESTIONS = [
  "Why was I flagged?",
  "What courses am I taking?",
  "Show my GPA trend",
  "What should I do next?",
  "How am I doing in Moodle?",
  "What should I discuss with my advisor?",
];

/**
 * mode="staff" (default): advisor assistant, may ask about any student.
 * mode="self": the signed-in student's own assistant - the backend scopes every answer
 * to the student id inside the JWT, so no student id is ever sent from the browser.
 */
export default function ChatPanel({ studentId, studentName, height = "h-[28rem]", mode = "staff" }: {
  studentId?: string | null;
  studentName?: string;
  height?: string;
  mode?: "staff" | "self";
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([
      {
        sender: "bot",
        text: mode === "self"
          ? `Hi${studentName ? ` ${studentName.split(" ")[0]}` : ""}! I'm your My Coach assistant. Ask me about your courses, GPA, alerts or next steps — my answers come only from your own synchronised RosarioSIS / Moodle record.`
          : studentId
            ? `I'm the My Coach advising assistant. Ask me about **${studentName || studentId}** — my answers come only from the synchronised RosarioSIS / Moodle data and the stored alerts.`
            : "I'm the My Coach advising assistant. Pick a student or mention a student ID / name in your question.",
      },
    ]);
  }, [studentId, studentName, mode]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setMessages((m) => [...m, { sender: "user", text: message }]);
    setInput("");
    setBusy(true);
    try {
      const r = mode === "self" ? await api.myChat(message) : await api.chat(message, studentId);
      setMessages((m) => [...m, { sender: "bot", text: r.response }]);
    } catch (e) {
      setMessages((m) => [...m, { sender: "bot", text: `⚠️ ${e instanceof Error ? e.message : "The assistant is unavailable."}` }]);
    } finally {
      setBusy(false);
    }
  };

  const suggestions = mode === "self" ? SELF_QUESTIONS : studentId ? STUDENT_QUESTIONS : GENERAL_QUESTIONS;

  return (
    <div className="flex flex-col">
      <div className={`scroll-thin ${height} space-y-3 overflow-y-auto bg-slate-50 p-4`}>
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[88%] rounded-2xl px-4 py-2.5 shadow-sm ${
                m.sender === "user" ? "rounded-br-sm bg-brand-900 text-sm text-white" : "rounded-bl-sm border border-slate-200 bg-white"
              }`}
            >
              {m.sender === "user" ? m.text : <Markdown text={m.text} />}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Spinner className="h-3 w-3" /> {mode === "self" ? "Looking up your record…" : "Looking up the student record…"}
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div className="flex flex-wrap gap-1.5 border-t border-slate-100 px-3 pt-3">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            disabled={busy}
            className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 transition hover:border-brand-700 hover:text-brand-800 disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={mode === "self" ? "Ask about your progress…" : studentId ? "Ask about this student…" : "Ask a question…"}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-700/20"
          aria-label="Message"
        />
        <button type="submit" disabled={busy || !input.trim()} className="rounded-lg bg-brand-900 px-4 text-sm font-semibold text-white hover:bg-brand-800 disabled:opacity-50">
          Send
        </button>
      </form>
    </div>
  );
}
