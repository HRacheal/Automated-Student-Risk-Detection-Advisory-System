# backend/alert_engine.py
from sqlalchemy.orm import Session
from models import Student, LMSActivity, AdvisingRule

def evaluate_student_alerts(student, lms_data):
    """
    Evaluates rule constraints on individual student objects and LMS telemetry.
    """
    anomalies = []
    risk_level = "Green"
    category = "Safe"

    gpa = float(student.cumulative_gpa) if student.cumulative_gpa else 0.0
    units = student.completed_units or 0
    standing = student.class_standing or ""
    
    # Safely map attributes matching database columns
    logins = lms_data.lms_login_frequency_per_week if lms_data else 0
    missed = lms_data.missed_assignments_count if lms_data else 0

    # Rule 1: GPA Critical Risk
    if gpa < 2.0:
        anomalies.append(f"Critical GPA Alert: Cumulative GPA is {gpa} (Below academic probation threshold 2.0)")
        risk_level = "Red"
        category = "Grade Trends"
    elif gpa < 2.5:
        anomalies.append(f"GPA Warning: GPA is {gpa} (Borderline academic status)")
        if risk_level != "Red":
            risk_level = "Yellow"
            category = "Grade Trends"

    # Rule 2: Undeclared Major Progression Alert
    if "Sophomore" in standing and student.declared_major and "Undeclared" in student.declared_major:
        anomalies.append("Academic Progression: Student is Sophomore year with no declared major")
        if risk_level != "Red":
            risk_level = "Yellow"
            category = "Academic Progression"

    # Rule 3: LMS Low Engagement & Missed Assignments Alert
    if logins < 3 or missed >= 3:
        anomalies.append(f"LMS Engagement Alert: Only {logins} logins/week and {missed} missed assignments")
        risk_level = "Red"
        category = "Wasted Hours"

    if not anomalies:
        anomalies.append("Student in good standing. No risk alerts triggered.")

    return {
        "risk_level": risk_level,
        "anomaly_category": category,
        "anomalies": anomalies
    }


def run_rule_engine(student: Student, lms_data: LMSActivity):
    """
    Wrapper function called by main.py to extract and return just the 
    list of alert strings for endpoint integration.
    """
    result = evaluate_student_alerts(student, lms_data)
    return result["anomalies"]


def check_advisory_rules(db: Session, student_units: int):
    """
    Queries database advising rules and matches action limits.
    """
    rules = db.query(AdvisingRule).all()
    applicable_actions = []
    
    for rule in rules:
        if rule.condition_detail and "Completed Units" in rule.condition_detail:
            applicable_actions.append(rule.action_or_limit)
            
    return {"matched_rules": applicable_actions}