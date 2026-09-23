# backend/main.py
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db
from analytics_engine import (
    train_xgboost_and_shap,
    run_transformer_sequence_analysis,
)
from alert_engine import check_advisory_rules

# Initialize database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="My Coach - ADSS Unified Detection & Advisory System")

# CORS CONFIGURATION
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.56.1:3000",
        "http://127.0.0.1:5500",  
        "http://localhost:5500",
        "null",
        "https://automated-student-risk-detection-ad.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ==========================================
# MULTI-TABLE SEARCH ENDPOINT (Queries all 5 tables)
# ==========================================
@app.get("/api/students/search")
def search_students(q: str = Query("", description="Search query for name or ID"), db: Session = Depends(get_db)):
    try:
        # Pull records from ALL 5 tables shown in your database schema:
        # 1. students, 2. lms_activity, 3. student_course_history, 4. courses, 5. advising_rules
        all_students = db.query(models.Student).all()
        all_lms = db.query(models.LMSActivity).all()
        
        try:
            all_history = db.query(models.StudentCourseHistory).all() if hasattr(models, 'StudentCourseHistory') else []
        except Exception:
            all_history = []
            
        try:
            all_courses = db.query(models.Course).all() if hasattr(models, 'Course') else []
        except Exception:
            all_courses = []
            
        try:
            all_rules = db.query(models.AdvisingRule).all() if hasattr(models, 'AdvisingRule') else []
        except Exception:
            all_rules = []

        # Create quick lookup mappings for telemetry and course history
        lms_map = {l.student_id: l for l in all_lms}
        
        history_map = {}
        for h in all_history:
            s_id = getattr(h, 'student_id', None)
            if s_id:
                if s_id not in history_map:
                    history_map[s_id] = []
                history_map[s_id].append(h)

        # Safe Python-level search across all loaded student records
        if q:
            q_lower = q.strip().lower()
            filtered_students = []
            for s in all_students:
                s_name = str(getattr(s, 'full_name', '')).lower()
                s_id = str(getattr(s, 'student_id', ''))
                if q_lower in s_name or q_lower in s_id:
                    filtered_students.append(s)
            students = filtered_students
        else:
            students = all_students

        student_list = []
        for s in students:
            s_id = s.student_id
            lms = lms_map.get(s_id)
            student_history = history_map.get(s_id, [])
            
            gpa = float(s.cumulative_gpa) if s.cumulative_gpa else 0.0
            missed = getattr(lms, 'missed_assignments_count', 0) if lms else 0
            logins = getattr(lms, 'lms_login_frequency_per_week', 0) if lms else 0

            # Derive risk levels dynamically using multi-table telemetry
            if gpa < 2.0 or missed >= 3 or logins < 3:
                risk_level = "Red"
                anomaly_category = "Grade Trends"
            elif gpa < 2.5:
                risk_level = "Yellow"
                anomaly_category = "Academic Progression"
            else:
                risk_level = "Green"
                anomaly_category = "Progression"

            risk_level = getattr(s, 'risk_level', risk_level) or risk_level
            anomaly_category = getattr(s, 'anomaly_category', anomaly_category) or anomaly_category

            anomalies_list = getattr(s, 'anomalies', [])
            if not anomalies_list:
                anomalies_list = [
                    f"Cumulative GPA: {gpa}", 
                    f"Missed Assignments: {missed}", 
                    f"Course History Records: {len(student_history)}"
                ]

            student_list.append({
                "student_id": s_id,
                "full_name": s.full_name,
                "class_standing": getattr(s, 'class_standing', 'Sophomore'),
                "risk_level": risk_level,
                "declared_major": getattr(s, 'declared_major', 'Computer Science'),
                "anomaly_category": anomaly_category,
                "registration_hold": getattr(s, 'registration_hold', False),
                "hold_reason": getattr(s, 'hold_reason', None),
                "tuition_balance": getattr(s, 'tuition_balance', 0.0),
                "cumulative_gpa": gpa,
                "anomalies": anomalies_list,
                "lms_engagement": {
                    "weekly_logins": logins,
                    "missed_assignments": missed
                },
                "total_courses_tracked": len(student_history)
            })

        return {"students": student_list}

    except Exception as e:
        print(f"Database error during multi-table student search: {e}")
        return {"students": []}


# ==========================================
# ADVISORY CHATBOT ENDPOINT
# ==========================================
@app.post("/api/chat", response_model=schemas.ChatResponse)
def advisory_chatbot(req: schemas.ChatRequest, db: Session = Depends(get_db)):
    msg = req.message.lower()
    import re

    # Inspect all 5 tables dynamically for chatbot context
    all_students = db.query(models.Student).all()
    all_lms = db.query(models.LMSActivity).all()
    all_rules = db.query(models.AdvisingRule).all() if hasattr(models, 'AdvisingRule') else []
    
    try:
        all_courses = db.query(models.Course).all() if hasattr(models, 'Course') else []
    except Exception:
        all_courses = []
        
    try:
        all_history = db.query(models.StudentCourseHistory).all() if hasattr(models, 'StudentCourseHistory') else []
    except Exception:
        all_history = []

    # Check for Student ID in query
    match = re.search(r'\b(\d{6})\b', msg)
    student_id = req.student_id or (int(match.group(1)) if match else None)

    if student_id:
        student = next((s for s in all_students if s.student_id == student_id), None)
        if not student:
            raise HTTPException(status_code=404, detail=f"Student ID {student_id} not found in database.")

        lms = next((l for l in all_lms if l.student_id == student_id), None)
        history_records = [h for h in all_history if getattr(h, 'student_id', None) == student_id]
        
        gpa = float(student.cumulative_gpa) if student.cumulative_gpa else 0.0
        missed = lms.missed_assignments_count if (lms and lms.missed_assignments_count) else 0
        logins = lms.lms_login_frequency_per_week if (lms and lms.lms_login_frequency_per_week) else 0

        if gpa < 2.0 or missed >= 3 or logins < 3:
            risk = "Red (High Risk)"
            next_steps = "Mandatory academic advising session within 5 business days. Enroll in peer tutoring."
        elif gpa < 2.5:
            risk = "Yellow (Borderline Risk)"
            next_steps = "Schedule a check-in with your assigned faculty advisor. Increase weekly LMS logins."
        else:
            risk = "Green (Good Standing)"
            next_steps = "Maintain current trajectory. Explore honors or internship opportunities."

        response_text = f"### Student Profile Analysis: {student.full_name} (ID: {student.student_id})\n\n"
        response_text += f"- **Major:** {student.declared_major} | Cumulative GPA: {gpa}\n"
        response_text += f"- **LMS Telemetry:** {logins} logins/week | {missed} missed assignments\n"
        response_text += f"- **Course History Records:** {len(history_records)} courses tracked across student history\n"
        response_text += f"- **Risk Tier:** {risk}\n\n"
        response_text += f"**Recommended Next Steps & Actions:**\n* {next_steps}"

        return schemas.ChatResponse(response=response_text)

    # Dynamic Course Table Inspection
    matched_course = None
    for course in all_courses:
        c_code = str(getattr(course, 'code', getattr(course, 'course_code', ''))).lower()
        c_name = str(getattr(course, 'name', getattr(course, 'course_name', ''))).lower()
        
        query_clean = msg.replace(" ", "")
        code_clean = c_code.replace(" ", "")
        
        if (code_clean and code_clean in query_clean) or any(term in query_clean for term in [code_clean, c_name] if len(term) > 3):
            matched_course = course
            break

    if matched_course:
        code = getattr(matched_course, 'code', getattr(matched_course, 'course_code', 'APT2060'))
        name = getattr(matched_course, 'name', getattr(matched_course, 'course_name', 'Course Name'))
        prereq = getattr(matched_course, 'prerequisite', getattr(matched_course, 'prerequisites', 'None'))
        level = getattr(matched_course, 'level', '2000-level')
        units = getattr(matched_course, 'units', '3')

        response_text = f"**Course Audit: {code} ({name})**\n\n"
        response_text += f"• **Prerequisite:** {prereq}\n"
        response_text += f"• **Level:** {level}\n"
        response_text += f"• **Units:** {units} units\n\n"
        response_text += f"**Recommended Next Steps:**\n"
        response_text += f"• Verify in your `student_course_history` table that you have completed **{prereq}** before registration.\n"
        response_text += f"• Submit a prerequisite waiver request if you have transfer credits."
        
        return schemas.ChatResponse(response=response_text)

    # Policy & Rule Lookups from Advising Rules Table
    if any(k in msg for k in ["retake", "repeat", "drop", "load", "unit", "graduation", "requirement"]):
        response_text = f"**USIU Institutional Policy & Rule Audit (Loaded {len(all_rules)} active rules):**\n\n"
        if "retake" in msg or "repeat" in msg or "drop" in msg:
            response_text += f"• Students may repeat a course once if a grade below C is obtained.\n"
            response_text += f"• Dropping core major courses without replacement triggers an automatic advisor review flag.\n\n"
            response_text += f"**Recommended Next Steps:**\n• Consult the registrar before dropping core degree requirements."
        elif "load" in msg or "unit" in msg:
            response_text += f"• **Normal Full Load:** 12 to 18 units per semester.\n"
            response_text += f"• **Overload Rule:** Enrolling in over 18 units requires a cumulative GPA >= 3.50.\n\n"
            response_text += f"**Recommended Next Steps:**\n• Ensure your total registered units comply with your financial aid terms."
        else:
            response_text += f"• Graduation requires clearing all major core units, general education requirements, and major GPA thresholds.\n\n"
            response_text += f"**Recommended Next Steps:**\n• Run a degree audit in your portal to check remaining requirements."
            
        return schemas.ChatResponse(response=response_text)

    # General Fallback
    return schemas.ChatResponse(response=f"I inspected all 5 database tables (`students`, `lms_activity`, `student_course_history`, `courses`, `advising_rules`). Please specify a valid course code, policy topic, or Student ID.")