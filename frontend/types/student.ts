// types/student.ts

export type RiskLevel = 'Red' | 'Yellow' | 'Green';
export type GPATrend = 'declining' | 'stable' | 'improving';
export type AnomalyCategory = 
  | 'Wasted Hours' 
  | 'Grade Trends' 
  | 'Academic Progression' 
  | 'Financial' 
  | 'LMS Engagement' 
  | 'None';

export interface LMSEngagement {
  weekly_logins: number;
  missed_assignments: number;
  gatekeeper_dropped: boolean;
  dropped_course_code: string;
}

export interface Student {
  student_id: number;
  full_name: string;
  declared_major: string;
  class_standing: string;
  cumulative_gpa: number;
  gpa_trend: GPATrend;
  completed_units: number;
  tuition_balance: number;
  registration_hold: boolean;
  hold_reason: string;
  risk_level: RiskLevel;
  anomaly_category: AnomalyCategory;
  anomalies: string[];
  lms_engagement: LMSEngagement;
}

export interface ChatMessage {
  sender: 'user' | 'bot';
  text: string;
}