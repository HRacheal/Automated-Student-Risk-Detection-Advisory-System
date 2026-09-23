// Dataset incorporating all handwritten anomaly triggers
const studentsData = [
    {
        student_id: 664101,
        full_name: "Kevin Kimani",
        declared_major: "Data Science & Analytics",
        class_standing: "Year 2 (Sophomore)",
        cumulative_gpa: 2.15,
        gpa_trend: "declining",
        completed_units: 42,
        current_enrolled_units: 9, // Anomaly: Underload (<12 units)
        tuition_balance: 0,
        registration_hold: false,
        hold_reason: "None",
        risk_level: "Red",
        anomaly_category: "Wasted Hours",
        anomalies: [
            "Enrolled in ACC2010 (Accounting) despite being DSA major[cite: 6, 7]",
            "Enrolled in 2000-level courses without required prerequisites[cite: 6, 7]",
            "Underload course load (9 units instead of 12-18 standard units)[cite: 6, 7]"
        ],
        lms_engagement: {
            weekly_logins: 2,
            missed_assignments: 4,
            gatekeeper_dropped: true,
            dropped_course_code: "APT1030"
        }
    },
    {
        student_id: 665220,
        full_name: "Amina Mohamed",
        declared_major: "Applied Computer Technology",
        class_standing: "Year 2 (Sophomore)",
        cumulative_gpa: 2.05,
        gpa_trend: "declining",
        completed_units: 36,
        current_enrolled_units: 15,
        tuition_balance: 0,
        registration_hold: false,
        hold_reason: "None",
        risk_level: "Red",
        anomaly_category: "Grade Trends",
        anomalies: [
            "Surviving on D/C- grades in key prerequisite courses (MTH1110)[cite: 6, 7]",
            "Repeatedly dropping gatekeeper courses (IST1020) and taking only general education electives[cite: 6, 7]",
            "Declining semester-over-semester GPA trend (3.1 -> 2.4 -> 2.05)[cite: 6, 7]"
        ],
        lms_engagement: {
            weekly_logins: 5,
            missed_assignments: 1,
            gatekeeper_dropped: true,
            dropped_course_code: "IST1020"
        }
    },
    {
        student_id: 663890,
        full_name: "Brian Omondi",
        declared_major: "Undeclared",
        class_standing: "Year 2 (Sophomore)",
        cumulative_gpa: 2.40,
        gpa_trend: "stable",
        completed_units: 54,
        current_enrolled_units: 12,
        tuition_balance: 0,
        registration_hold: false,
        hold_reason: "None",
        risk_level: "Yellow",
        anomaly_category: "Academic Progression",
        anomalies: [
            "Sophomore year with no declared major[cite: 6, 7]",
            "Excessive course withdrawals (W grades) across 2 consecutive semesters[cite: 6, 7]",
            "Unresolved incomplete grades (I grade in APT1050)[cite: 6, 7]"
        ],
        lms_engagement: {
            weekly_logins: 6,
            missed_assignments: 2,
            gatekeeper_dropped: false,
            dropped_course_code: "None"
        }
    },
    {
        student_id: 661044,
        full_name: "Joy Wanjiku",
        declared_major: "Software Engineering",
        class_standing: "Year 3 (Junior)",
        cumulative_gpa: 2.80,
        gpa_trend: "stable",
        completed_units: 78,
        current_enrolled_units: 0,
        tuition_balance: 145000,
        registration_hold: true,
        hold_reason: "Financial Hold (Unpaid Tuition Balance)[cite: 7]",
        risk_level: "Red",
        anomaly_category: "Financial",
        anomalies: [
            "Unpaid tuition balance flag prior to upcoming registration[cite: 7]",
            "Financial hold preventing registration for upcoming semester[cite: 7]"
        ],
        lms_engagement: {
            weekly_logins: 0,
            missed_assignments: 0,
            gatekeeper_dropped: false,
            dropped_course_code: "None"
        }
    },
    {
        student_id: 667812,
        full_name: "Daniel Otieno",
        declared_major: "Information Systems Technology",
        class_standing: "Year 1 (Freshman)",
        cumulative_gpa: 1.90,
        gpa_trend: "declining",
        completed_units: 15,
        current_enrolled_units: 15,
        tuition_balance: 0,
        registration_hold: false,
        hold_reason: "None",
        risk_level: "Red",
        anomaly_category: "LMS Engagement",
        anomalies: [
            "Early disengagement: 5 consecutive missed quiz/assignment submissions on Blackboard[cite: 7]",
            "Dropped course mid-semester without adding a replacement course[cite: 7]",
            "Zero advisor interaction logged during registration window[cite: 7]"
        ],
        lms_engagement: {
            weekly_logins: 1,
            missed_assignments: 5,
            gatekeeper_dropped: true,
            dropped_course_code: "APT1020"
        }
    },
    {
        student_id: 668901,
        full_name: "Grace Muthoni",
        declared_major: "Data Science & Analytics",
        class_standing: "Year 3 (Junior)",
        cumulative_gpa: 3.65,
        gpa_trend: "improving",
        completed_units: 90,
        current_enrolled_units: 15,
        tuition_balance: 0,
        registration_hold: false,
        hold_reason: "None",
        risk_level: "Green",
        anomaly_category: "None",
        anomalies: [
            "No anomalies detected. Progressing normally according to major curriculum map."
        ],
        lms_engagement: {
            weekly_logins: 12,
            missed_assignments: 0,
            gatekeeper_dropped: false,
            dropped_course_code: "None"
        }
    }
];

// Tab Navigation Logic
function switchTab(tabName) {
    ['dashboard', 'student', 'chatbot'].forEach(t => {
        document.getElementById(`tab-${t}-view`).classList.add('hidden');
        document.getElementById(`nav-${t}`).className = "tab-btn text-xs font-semibold px-3 py-1.5 rounded-lg text-indigo-200 hover:text-white transition";
    });

    document.getElementById(`tab-${tabName}-view`).classList.remove('hidden');
    document.getElementById(`nav-${tabName}`).className = "tab-btn active text-xs font-semibold px-3 py-1.5 rounded-lg transition";
}

// Update KPI Counts
function updateStats() {
    document.getElementById('statTotal').innerText = studentsData.length;
    let red = 0, yellow = 0, green = 0;
    studentsData.forEach(s => {
        if (s.risk_level === 'Red') red++;
        else if (s.risk_level === 'Yellow') yellow++;
        else green++;
    });

    document.getElementById('statRed').innerText = red;
    document.getElementById('statYellow').innerText = yellow;
    document.getElementById('statGreen').innerText = green;
}

// Render Dashboard Student Grid
function renderStudents() {
    const grid = document.getElementById('studentCardGrid');
    const search = document.getElementById('studentSearch').value.toLowerCase();
    const filter = document.getElementById('filterAnomaly').value;

    grid.innerHTML = "";

    const filtered = studentsData.filter(s => {
        const matchesSearch = s.full_name.toLowerCase().includes(search) || s.student_id.toString().includes(search);
        const matchesCategory = filter === "ALL" || s.anomaly_category === filter;
        return matchesSearch && matchesCategory;
    });

    if (filtered.length === 0) {
        grid.innerHTML = `<div class="col-span-full p-8 text-center text-slate-400 text-xs">No student records found matching active filters.</div>`;
        return;
    }

    filtered.forEach(s => {
        let badgeColor = "bg-emerald-100 text-emerald-800 border-emerald-300";
        if (s.risk_level === 'Red') badgeColor = "bg-red-100 text-red-800 border-red-300";
        if (s.risk_level === 'Yellow') badgeColor = "bg-amber-100 text-amber-800 border-amber-300";

        grid.innerHTML += `
            <div class="student-card bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="font-bold text-sm text-slate-800">${s.full_name}</h3>
                        <p class="text-xs text-slate-500">ID: ${s.student_id} | ${s.class_standing}</p>
                    </div>
                    <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeColor}">
                        ${s.risk_level} Risk
                    </span>
                </div>
                
                <div class="text-xs space-y-1 text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100">
                    <div class="flex justify-between">
                        <span class="text-slate-500">Major:</span>
                        <span class="font-semibold ${s.declared_major === 'Undeclared' ? 'text-red-600' : 'text-slate-800'}">${s.declared_major}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-500">GPA Trend:</span>
                        <span class="font-semibold ${s.gpa_trend === 'declining' ? 'text-red-600' : 'text-slate-800'}">${s.cumulative_gpa} (${s.gpa_trend})</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-500">Primary Anomaly:</span>
                        <span class="font-bold text-indigo-700">${s.anomaly_category}</span>
                    </div>
                </div>

                <button onclick="viewStudentProfile(${s.student_id})" class="w-full text-center bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold py-1.5 rounded-lg border border-indigo-100 transition">
                    Audit Anomaly Triggers
                </button>
            </div>
        `;
    });
}

// Render Individual Audit Profile View
function viewStudentProfile(studentId) {
    const s = studentsData.find(item => item.student_id === studentId);
    if (!s) return;

    const container = document.getElementById('studentDetailContainer');
    const percent = Math.min(100, Math.round((s.completed_units / 150) * 100));

    let anomaliesHtml = s.anomalies.map(a => `<li class="flex items-start gap-2"><i class="fa-solid fa-triangle-exclamation text-red-500 mt-0.5"></i> ${a}</li>`).join('');

    container.innerHTML = `
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-4">
            <div>
                <span class="text-xs font-semibold text-indigo-600 uppercase tracking-wider">USIU Anomaly Audit Log</span>
                <h2 class="text-xl font-bold text-slate-800">${s.full_name} (ID: ${s.student_id})</h2>
                <p class="text-xs text-slate-500">Major: ${s.declared_major} | ${s.class_standing}</p>
            </div>
            ${s.registration_hold ? 
                `<div class="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg text-xs font-medium">
                    <i class="fa-solid fa-triangle-exclamation mr-1"></i> ${s.hold_reason} (KES${s.tuition_balance.toLocaleString()})
                </div>` : 
                `<div class="bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-2 rounded-lg text-xs font-medium">
                    <i class="fa-solid fa-circle-check mr-1"></i> Registration Clear
                </div>`}
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Anomaly Alerts Column -->
            <div class="bg-red-50/50 p-5 rounded-xl border border-red-200 space-y-3">
                <h3 class="font-bold text-xs text-red-800 uppercase tracking-wider flex items-center gap-2">
                    <i class="fa-solid fa-bolt text-red-600"></i> Triggered Risk Flags
                </h3>
                <ul class="text-xs space-y-2 text-slate-700">
                    ${anomaliesHtml}
                </ul>
            </div>

            <!-- LMS & Performance Column -->
            <div class="bg-slate-50 p-5 rounded-xl border border-slate-200 space-y-3">
                <h3 class="font-bold text-xs text-slate-700 uppercase tracking-wider">Blackboard & Academic Indicators</h3>
                <div class="text-xs space-y-2 text-slate-600">
                    <div class="flex justify-between py-1 border-b">
                        <span>Cumulative GPA:</span>
                        <span class="font-bold text-slate-800">${s.cumulative_gpa} / 4.00 (${s.gpa_trend})</span>
                    </div>
                    <div class="flex justify-between py-1 border-b">
                        <span>Weekly Blackboard Logins:</span>
                        <span class="font-bold text-slate-800">${s.lms_engagement.weekly_logins} logins/week</span>
                    </div>
                    <div class="flex justify-between py-1 border-b">
                        <span>Missed LMS Assignments:</span>
                        <span class="font-bold ${s.lms_engagement.missed_assignments > 2 ? 'text-red-600' : 'text-slate-800'}">${s.lms_engagement.missed_assignments} missed</span>
                    </div>
                    <div class="flex justify-between py-1">
                        <span>Gatekeeper Course Status:</span>
                        <span class="font-bold ${s.lms_engagement.gatekeeper_dropped ? 'text-red-600' : 'text-emerald-600'}">
                            ${s.lms_engagement.gatekeeper_dropped ? `Dropped (${s.lms_engagement.dropped_course_code})` : 'Normal Progress'}
                        </span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Degree Progress Bar -->
        <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
            <div class="flex justify-between text-xs text-slate-600">
                <span>Degree Completion Audit</span>
                <span class="font-bold">${s.completed_units} / 150 Units Earned (${percent}%)</span>
            </div>
            <div class="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
                <div class="bg-indigo-600 h-full rounded-full" style="width: ${percent}%"></div>
            </div>
        </div>
    `;

    switchTab('student');
}

window.onload = function() {
    updateStats();
    renderStudents();
};