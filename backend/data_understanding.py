# backend/data_understanding.py
import pandas as pd
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Student, LMSActivity, Course, StudentCourseHistory, AdvisingRule

def profile_database():
    db: Session = SessionLocal()
    try:
        print("--- 1. DATA UNDERSTANDING & PROFILING ---")
        
        # Load tables into DataFrames
        df_students = pd.read_sql(db.query(Student).statement, db.bind)
        df_lms = pd.read_sql(db.query(LMSActivity).statement, db.bind)
        df_courses = pd.read_sql(db.query(Course).statement, db.bind)
        df_history = pd.read_sql(db.query(StudentCourseHistory).statement, db.bind)
        df_rules = pd.read_sql(db.query(AdvisingRule).statement, db.bind)
        
        # Quick exploratory checks
        print(f"Total Students Loaded: {len(df_students)}[cite: 10]")
        print(f"Total LMS Records Loaded: {len(df_lms)}[cite: 8]")
        print(f"Total Courses Available: {len(df_courses)}[cite: 7]")
        
        print("\nRisk Level Distribution in LMS Activity:")
        print(df_lms['risk_level'].value_counts())[cite: 8]
        
        print("\nMissing Values Check (Students Table):")
        print(df_students.isnull().sum())[cite: 10]
        
        return "Data understanding profile completed successfully."
    finally:
        db.close()

if __name__ == "__main__":
    print(profile_database())