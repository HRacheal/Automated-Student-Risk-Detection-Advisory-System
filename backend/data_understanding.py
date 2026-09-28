# backend/data_understanding.py
"""
Profiles the application database (reference + legacy tables).
Run from backend/:  python data_understanding.py
"""
import pandas as pd
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AdvisingRule, AnomalyAlert, Course, LMSActivity, Student, StudentCourseHistory


def profile_database():
    db: Session = SessionLocal()
    try:
        print("--- DATA UNDERSTANDING & PROFILING ---")
        df_students = pd.read_sql(db.query(Student).statement, db.bind)
        df_lms = pd.read_sql(db.query(LMSActivity).statement, db.bind)
        df_courses = pd.read_sql(db.query(Course).statement, db.bind)
        df_history = pd.read_sql(db.query(StudentCourseHistory).statement, db.bind)
        df_rules = pd.read_sql(db.query(AdvisingRule).statement, db.bind)
        df_alerts = pd.read_sql(db.query(AnomalyAlert).statement, db.bind)

        print(f"Legacy students (ML training set): {len(df_students)}")
        print(f"Legacy LMS records:                {len(df_lms)}")
        print(f"Legacy course history records:     {len(df_history)}")
        print(f"Course catalogue entries:          {len(df_courses)}")
        print(f"Advising rules:                    {len(df_rules)}")
        print(f"Anomaly alerts stored:             {len(df_alerts)}")

        print("\nRisk label distribution in legacy LMS activity:")
        print(df_lms["risk_level"].value_counts())

        print("\nMissing values (legacy students table):")
        print(df_students.isnull().sum())

        if not df_alerts.empty:
            print("\nStored alerts by type and status:")
            print(df_alerts.groupby(["anomaly_type", "status"]).size())
        return "Data understanding profile completed successfully."
    finally:
        db.close()


if __name__ == "__main__":
    print(profile_database())
