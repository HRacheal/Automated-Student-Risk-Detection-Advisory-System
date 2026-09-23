// data/students.ts
import { Student } from '../types/student';

export const studentsData: Student[] = [
  {
    student_id: 664101,
    full_name: "Kevin Kimani",
    declared_major: "Data Science & Analytics",
    class_standing: "Year 2 (Sophomore)",
    cumulative_gpa: 2.15,
    gpa_trend: "declining",
    completed_units: 42,
    tuition_balance: 0,
    registration_hold: false,
    hold_reason: "None",
    risk_level: "Red",
    anomaly_category: "Wasted Hours",
    anomalies: [
      "Enrolled in ACC2010 (Accounting) despite being DSA major",
      "Enrolled in 2000-level courses without required prerequisites",
      "Underload course load (9 units instead of 12-18 standard units)"
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
    tuition_balance: 0,
    registration_hold: false,
    hold_reason: "None",
    risk_level: "Red",
    anomaly_category: "Grade Trends",
    anomalies: [
      "Surviving on D/C- grades in key prerequisite courses (MTH1110)",
      "Repeatedly dropping gatekeeper courses (IST1020) and taking general electives",
      "Declining semester-over-semester GPA trend (3.1 -> 2.4 -> 2.05)"
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
    tuition_balance: 0,
    registration_hold: false,
    hold_reason: "None",
    risk_level: "Yellow",
    anomaly_category: "Academic Progression",
    anomalies: [
      "Sophomore year with no declared major",
      "Excessive course withdrawals (W grades) across 2 consecutive semesters",
      "Unresolved incomplete grades (I grade in APT1050)"
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
    tuition_balance: 145000,
    registration_hold: true,
    hold_reason: "Financial Hold (Unpaid Tuition Balance)",
    risk_level: "Red",
    anomaly_category: "Financial",
    anomalies: [
      "Unpaid tuition balance flag prior to upcoming registration",
      "Financial hold preventing registration for upcoming semester"
    ],
    lms_engagement: {
      weekly_logins: 0,
      missed_assignments: 0,
      gatekeeper_dropped: false,
      dropped_course_code: "None"
    }
  }
];