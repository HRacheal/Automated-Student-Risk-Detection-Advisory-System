// app/page.tsx
"use client";

import { useState, useEffect } from "react";
import { Student, ChatMessage } from "../types/student";

export default function EduSentinelDashboard() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "student" | "chatbot">("dashboard");
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedFilter, setSelectedFilter] = useState<string>("ALL");

  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [chatInput, setChatInput] = useState<string>("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      sender: "bot",
      text: "Hello! Ask me about student risk IDs, prerequisites for courses (e.g. APT2060), course loads, or retake policies."
    }
  ]);

  useEffect(() => {
    async function fetchStudents() {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/students/search?q=${encodeURIComponent(searchQuery)}`);
        const data = await response.json();
        setStudents(data.students || []);
      } catch (error) {
        console.error("Failed to connect to FastAPI backend:", error);
      } finally {
        setLoading(false);
      }
    }

    const timer = setTimeout(() => {
      fetchStudents();
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const totalTracked = students.length;
  const redAlerts = students.filter((s) => s.risk_level === "Red").length;
  const yellowWarnings = students.filter((s) => s.risk_level === "Yellow").length;
  const greenSafe = students.filter((s) => s.risk_level === "Green").length;

  const filteredStudents = students.filter((s) => {
    return selectedFilter === "ALL" || s.anomaly_category === selectedFilter;
  });

  const handleSendMessage = async (): Promise<void> => {
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    const newMessages: ChatMessage[] = [...chatMessages, { sender: "user", text: userMsg }];
    setChatMessages(newMessages);
    setChatInput("");

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg })
      });
      
      if (res.ok) {
        const data = await res.json();
        setChatMessages((prev) => [...prev, { sender: "bot", text: data.response }]);
        return;
      }
    } catch (e) {
      console.warn("Backend chat route unavailable, falling back to local client parsing:", e);
    }

    const query = userMsg.toLowerCase();
    let response = "I could not find a direct match in the USIU Course Advisory database. Please consult your academic advisor.";

    if (query.includes("apt2060")) {
      response = "Course Audit: APT2060 (Data Structures & Algorithms)\n• Prerequisite: APT1030 or MTH1110\n• Level: 2000-level\n• Units: 3 units";
    } else if (query.includes("retake") || query.includes("repeat")) {
      response = "USIU Course Retake Policy:\n• Students may repeat a course once if a grade below C is obtained.\n• Dropping gatekeeper courses without replacement flags an advisor alert.";
    } else if (query.includes("load") || query.includes("unit")) {
      response = "Course Load Rules:\n• Normal Load: 12 to 18 units/semester.\n• Underload (<12 units) requires registrar approval.\n• Overload (>18 units) requires GPA >= 3.50.";
    }

    setChatMessages((prev) => [...prev, { sender: "bot", text: response }]);
  };

  return (
    <div className="bg-slate-100 min-h-screen font-sans text-slate-800 flex flex-col">
      <header className="bg-indigo-900 text-white shadow-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="bg-amber-400 text-indigo-950 font-black p-2 rounded-lg text-xl tracking-wider">
              USIU
            </div>
            <div>
              <h1 className="font-bold text-lg leading-tight">My coach</h1>
              <p className="text-xs text-indigo-200">
                Real-Time Academic Risk & Anomaly Detection System
              </p>
            </div>
          </div>

          <nav className="flex gap-1 bg-indigo-950/60 p-1 rounded-xl border border-indigo-700/50 my-2 sm:my-0">
            <button onClick={() => setActiveTab("dashboard")} className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition ${activeTab === "dashboard" ? "bg-indigo-800 text-white" : "text-indigo-200 hover:text-white"}`}>
              Risk Dashboard
            </button>
            <button onClick={() => setActiveTab("student")} className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition ${activeTab === "student" ? "bg-indigo-800 text-white" : "text-indigo-200 hover:text-white"}`}>
              Student Audit Profile
            </button>
            <button onClick={() => setActiveTab("chatbot")} className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition ${activeTab === "chatbot" ? "bg-indigo-800 text-white" : "text-indigo-200 hover:text-white"}`}>
              Advisory Bot
            </button>
          </nav>

          <div className="flex items-center gap-2 text-xs">
            <span className="bg-emerald-950 text-emerald-300 border border-emerald-800 px-2.5 py-1 rounded-full font-medium flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              Engine Active (Supabase)
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-4 sm:p-6 flex-1 w-full space-y-6">
        {activeTab === "dashboard" && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-500 font-medium">Total Tracked</p>
                  <h3 className="text-2xl font-bold text-slate-800">{totalTracked}</h3>
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-red-200 shadow-sm flex items-center justify-between">
                <div>
                  <p className="text-xs text-red-600 font-medium">Red Alerts (High Risk)</p>
                  <h3 className="text-2xl font-bold text-red-600">{redAlerts}</h3>
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-amber-200 shadow-sm flex items-center justify-between">
                <div>
                  <p className="text-xs text-amber-600 font-medium">Yellow Warnings</p>
                  <h3 className="text-2xl font-bold text-amber-600">{yellowWarnings}</h3>
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-emerald-200 shadow-sm flex items-center justify-between">
                <div>
                  <p className="text-xs text-emerald-600 font-medium">Green Safe</p>
                  <h3 className="text-2xl font-bold text-emerald-600">{greenSafe}</h3>
                </div>
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
              <input type="text" placeholder="Search student name or 6-digit ID..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full md:w-80 px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" />
              <select value={selectedFilter} onChange={(e) => setSelectedFilter(e.target.value)} className="text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50 outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="ALL">All Anomaly Types</option>
                <option value="Wasted Hours">Wasted Hours (Course/Major Mismatch)</option>
                <option value="Grade Trends">Grade Trends (Marginal Passes / Drops)</option>
                <option value="Academic Progression">Progression (Holds / Delayed Major)</option>
                <option value="Financial">Financial / Administrative Holds</option>
              </select>
            </div>

            {loading ? (
              <p className="text-center text-xs text-slate-400 py-12">Loading live records from Supabase database...</p>
            ) : filteredStudents.length === 0 ? (
              <p className="text-center text-xs text-slate-400 py-12">No student records found matching active search filters.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredStudents.map((student) => (
                  <div key={student.student_id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3 hover:-translate-y-0.5 transition">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-bold text-sm text-slate-800">{student.full_name}</h3>
                        <p className="text-xs text-slate-500">ID: {student.student_id} | {student.class_standing}</p>
                      </div>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${student.risk_level === "Red" ? "bg-red-100 text-red-800 border-red-300" : student.risk_level === "Yellow" ? "bg-amber-100 text-amber-800 border-amber-300" : "bg-emerald-100 text-emerald-800 border-emerald-300"}`}>
                        {student.risk_level} Risk
                      </span>
                    </div>
                    <div className="text-xs space-y-1 text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Major:</span>
                        <span className="font-semibold text-slate-800">{student.declared_major}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Primary Anomaly:</span>
                        <span className="font-bold text-indigo-700">{student.anomaly_category}</span>
                      </div>
                    </div>
                    <button onClick={() => { setSelectedStudent(student); setActiveTab("student"); }} className="w-full text-center bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold py-1.5 rounded-lg border border-indigo-100 transition">
                      Audit Anomaly Triggers
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "student" && (
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-6">
            {selectedStudent ? (
              <>
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-4">
                  <div>
                    <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">USIU Anomaly Audit Log</span>
                    <h2 className="text-xl font-bold text-slate-800">{selectedStudent.full_name} (ID: {selectedStudent.student_id})</h2>
                    <p className="text-xs text-slate-500">Major: {selectedStudent.declared_major} | {selectedStudent.class_standing}</p>
                  </div>
                  {selectedStudent.registration_hold ? (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg text-xs font-medium">
                      ⚠️ {selectedStudent.hold_reason} (KES {selectedStudent.tuition_balance?.toLocaleString()})
                    </div>
                  ) : (
                    <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-2 rounded-lg text-xs font-medium">
                      ✓ Registration Clear
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-red-50/50 p-5 rounded-xl border border-red-200 space-y-3">
                    <h3 className="font-bold text-xs text-red-800 uppercase tracking-wider">⚡ Triggered Risk Flags</h3>
                    <ul className="text-xs space-y-2 text-slate-700">
                      {selectedStudent.anomalies?.map((a, i) => (
                        <li key={i} className="flex items-start gap-2"><span className="text-red-500">⚠️</span> {a}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-slate-50 p-5 rounded-xl border border-slate-200 space-y-3">
                    <h3 className="font-bold text-xs text-slate-700 uppercase tracking-wider">Academic & LMS Metrics</h3>
                    <div className="text-xs space-y-2 text-slate-600">
                      <div className="flex justify-between py-1 border-b">
                        <span>Cumulative GPA:</span>
                        <span className="font-bold text-slate-800">{selectedStudent.cumulative_gpa} / 4.00</span>
                      </div>
                      <div className="flex justify-between py-1 border-b">
                        <span>Weekly Blackboard Logins:</span>
                        <span className="font-bold text-slate-800">{selectedStudent.lms_engagement?.weekly_logins} logins/week</span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span>Missed Assignments:</span>
                        <span className="font-bold text-red-600">{selectedStudent.lms_engagement?.missed_assignments} missed</span>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-slate-400 text-xs text-center py-8">Select a student from the Risk Dashboard to view full anomaly details.</p>
            )}
          </div>
        )}

        {activeTab === "chatbot" && (
          <div className="max-w-3xl mx-auto bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col h-[500px]">
            <div className="p-4 bg-indigo-900 text-white rounded-t-xl">
              <h3 className="font-bold text-sm">USIU Academic Advisory Bot</h3>
              <p className="text-xs text-indigo-200">Prerequisite and student record lookup connected to Supabase</p>
            </div>
            <div className="flex-1 p-4 overflow-y-auto space-y-3 text-xs">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`p-3 rounded-lg max-w-lg whitespace-pre-line ${msg.sender === "user" ? "bg-indigo-50 text-indigo-950 ml-auto font-medium" : "bg-slate-100 text-slate-700"}`}>
                  {msg.text}
                </div>
              ))}
            </div>
            <div className="p-3 border-t border-slate-200 flex gap-2">
              <input type="text" placeholder="Ask e.g. What are prerequisites for APT2060 or student ID 664101?" value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSendMessage()} className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-indigo-500" />
              <button onClick={handleSendMessage} className="bg-indigo-600 text-white text-xs px-4 py-2 rounded-lg font-semibold hover:bg-indigo-700 transition">Send</button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}