export type Risk = "HIGH" | "MODERATE" | "LOW";
export type AlertStatus = "active" | "acknowledged" | "resolved" | "auto_resolved";

export type Role = "student" | "advisor" | "admin";

export interface User {
  email: string;
  name: string;
  role: Role;
  student_id?: string | null;
}

export interface StudentIndicator {
  title: string;
  severity: Risk;
  description: string;
  evidence: string[];
  recommended_action: string;
  detected_at: string;
}

export interface MyRecord {
  student: StudentRecord;
  risk_level: Risk;
  last_synced_at: string;
  indicators: StudentIndicator[];
}

export interface AdminOverview {
  viewer: { name: string | null; email: string; role: Role };
  api: { status: string; version: string };
  database: "ok" | "unavailable";
  sign_in: {
    student: boolean;
    advisor: boolean;
    admin: boolean;
    student_account_linked_record: string | null;
    student_record_synchronised: boolean;
  };
  configuration: {
    database_configured: boolean;
    jwt_configured: boolean;
    rosario_configured: boolean;
    moodle_configured: boolean;
    demo_data_enabled: boolean;
    session_hours: number;
  };
  usage: {
    students_monitored: number;
    demo_students: number;
    risk_counts: Record<Risk, number>;
    open_alerts: number;
    open_high_alerts: number;
    interventions: number;
    sync_runs: number;
  };
  sync_running: boolean;
  last_sync: SyncRun | null;
  last_successful_sync: SyncRun | null;
  ml: MLStatus;
}

export interface SyncStatus {
  running: boolean;
  last: SyncRun | null;
  last_successful: SyncRun | null;
}

export interface MLPrediction {
  status: "ok" | "unavailable" | "insufficient_data" | "error";
  reason?: string;
  probability_high_risk?: number;
  band?: Risk;
  top_factors?: { feature: string; value: number; contribution: number }[];
  model?: string;
  training_samples?: number;
  loocv_accuracy?: number;
  disclaimer?: string;
}

export interface StudentSummary {
  student_id: string;
  full_name: string;
  sources: string[];
  is_demo: boolean;
  declared_major: string | null;
  major_field_available: boolean;
  class_standing: string | null;
  cumulative_gpa: number | null;
  completed_units: number | null;
  current_course_count: number;
  risk_level: Risk;
  open_alerts: number;
  open_alerts_by_severity: Partial<Record<Risk, number>>;
  last_synced_at: string;
  ml_prediction: MLPrediction | null;
  unaddressed_alerts?: number;
}

export interface Alert {
  id: number;
  student_id: string;
  student_name: string | null;
  anomaly_type: string;
  title: string;
  severity: Risk;
  description: string;
  evidence: string[];
  recommended_intervention: string;
  status: AlertStatus;
  source: string;
  data_sources: string[];
  detected_at: string;
  last_seen_at: string;
  resolved_at: string | null;
}

export interface AlertEvent {
  id: number;
  alert_id: number;
  student_id: string;
  event_type: string;
  detail: string | null;
  actor: string | null;
  created_at: string;
}

export interface Intervention {
  id: number;
  student_id: string;
  student_name?: string | null;
  alert_id: number | null;
  action_type: string;
  notes: string | null;
  status: "planned" | "in_progress" | "completed";
  follow_up_date: string | null;
  advisor: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface SourceSummary {
  status: string;
  message: string;
  students: number;
  details?: Record<string, unknown>;
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "partial" | "failed";
  /** One sentence naming which sources were / were not synchronised. */
  summary: string;
  triggered_by: string | null;
  sources: Record<string, SourceSummary>;
  /** RosarioSIS students matched to a Moodle account in this run (null for runs before this was recorded). */
  joined_students: number | null;
  students_analyzed: number;
  anomalies_detected: number;
  new_alerts: number;
  resolved_alerts: number;
  error: string | null;
}

export interface DashboardSummary {
  total_students: number;
  risk_counts: Record<Risk, number>;
  active_alerts: number;
  alerts_by_type: { type: string; title: string; count: number }[];
  recent_anomalies: Alert[];
  students_requiring_intervention: StudentSummary[];
  last_sync: SyncRun | null;
}

export interface CourseEnrollment {
  code: string;
  title: string | null;
  units: number | null;
  status: "enrolled" | "dropped";
  start_date: string | null;
  end_date: string | null;
  term: string | null;
  source: string;
}

export interface CourseGrade {
  code: string;
  title: string | null;
  term: string | null;
  term_order: number | null;
  grade_letter: string | null;
  grade_percent: number | null;
  grade_points: number | null;
  credits_attempted: number | null;
  credits_earned: number | null;
  passed: boolean | null;
  withdrawn: boolean;
  incomplete: boolean;
}

export interface StudentRecord {
  student_id: string;
  full_name: string;
  sources: string[];
  is_demo: boolean;
  username: string | null;
  declared_major: string | null;
  major_field_available: boolean;
  school: string | null;
  grade_level: string | null;
  enrollment_status: string | null;
  enrollment_note: string | null;
  completed_units: number | null;
  class_standing: string | null;
  cumulative_gpa: number | null;
  term_gpas: { term: string; term_order: number; gpa: number; credits: number }[];
  current_term: string | null;
  current_courses: CourseEnrollment[];
  course_history: CourseGrade[];
  holds: string[] | null;
  financial: { available: boolean; balance: number | null; overdue_amount: number | null; fees_count: number; source: string };
  lms: {
    available: boolean;
    moodle_user_id: number | null;
    courses: string[];
    last_access: string | null;
    days_since_last_access: number | null;
    assignments: { course: string; name: string; due_date: string | null; status: string }[];
    quizzes: { course: string; name: string; percent: number | null }[];
    course_grades: Record<string, number | null>;
    capabilities: Record<string, boolean>;
  };
  unavailable: string[];
  missing: string[];
}

export interface StudentDetail {
  student: StudentRecord;
  risk_level: Risk;
  sources: string[];
  last_synced_at: string;
  sync_run_id: number;
  rules_evaluated: { rule: string; title: string }[];
  rules_skipped: { rule: string; title: string; reason: string }[];
  ml_prediction: MLPrediction | null;
  alerts: Alert[];
  events: AlertEvent[];
  interventions: Intervention[];
  risk_history: { synced_at: string; risk_level: Risk; sync_run_id: number }[];
}

export interface IntegrationStatus {
  rosario: { status: string; message: string };
  moodle: { status: string; message: string; functions?: string[] };
  demo: { status: string; message: string };
}

export interface TestLab {
  enabled: boolean;
  students: { student_id: string; full_name: string; declared_major: string | null }[];
  scenarios: { key: string; label: string; expected_anomaly: string; expected_title: string }[];
  active: Record<string, string[]>;
}

/** Output of backend/scripts/evaluate_models.py (served by GET /api/model-performance). */
export interface ConfusionMatrix {
  labels: string[];
  rows_actual_cols_predicted: number[][];
}

export interface NotEvaluable {
  evaluable: false;
  reason: string;
  model?: string;
  source?: string;
}

export interface ClassifierResult {
  key: string;
  label: string;
  selected: boolean;
  accuracy_pct: number;
  balanced_accuracy: number;
  precision_red: number;
  recall_red: number;
  f1_red: number;
  f1_macro: number;
  roc_auc: number;
  confusion_matrix: ConfusionMatrix;
  classification_report_text: string;
}

export interface MLClassifierEvaluation {
  evaluable: true;
  role: string;
  dataset: string;
  features: string[];
  classes: string[];
  class_counts: Record<string, number>;
  validation: string;
  test_set_size: number;
  baseline_majority_accuracy_pct: number;
  selection_rule: string;
  selected: string;
  models: ClassifierResult[];
  xgboost_diagnosis: string;
  caveat: string;
}

export interface SequenceMetrics {
  accuracy_pct: number;
  balanced_accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number | null;
  confusion_matrix: ConfusionMatrix;
  classification_report_text: string;
}

export interface DataGate {
  source: string;
  samples: number;
  positives: number;
  students: number;
  students_with_positive: number;
  gate: Record<string, boolean>;
  sufficient: boolean;
  decision?: string;
}

export interface TransformerEvaluation {
  evaluable: boolean;
  reason?: string;
  status?: string;
  target?: string;
  input_sequence?: string[];
  validation?: string;
  hyperparameters?: Record<string, number>;
  real_data?: DataGate;
  synthetic_data?: DataGate;
  transformer?: SequenceMetrics;
  baseline_logistic_regression?: SequenceMetrics;
  baseline_majority?: SequenceMetrics;
  seed_stability?: { f1_mean: number; f1_std: number; runs: { seed: number; f1: number; roc_auc: number }[] };
  caveat?: string;
  artifact?: string;
}

export interface RuleEngineEvaluation {
  evaluable: true;
  source: "pipeline" | "stored";
  note: string;
  test_set_size: number;
  classes: string[];
  accuracy_pct: number;
  precision_macro: number;
  recall_macro: number;
  f1_macro: number;
  f1_weighted: number;
  roc_auc_reason: string;
  confusion_matrix: ConfusionMatrix;
  classification_report_text: string;
  binary_at_risk: { accuracy_pct: number; precision: number; recall: number; f1: number; confusion_matrix: ConfusionMatrix };
  matches_engine_specification: number;
  misclassified: { student_id: string; scenario: string; expected: string; predicted: string }[];
}

export interface ModelPerformanceReport {
  generated_at: string;
  generated_by: string;
  rule_engine_pipeline: RuleEngineEvaluation | NotEvaluable;
  rule_engine_stored: RuleEngineEvaluation | NotEvaluable;
  ml_classifiers: MLClassifierEvaluation | NotEvaluable;
  transformer: TransformerEvaluation;
}

export interface MLStatus {
  trained: boolean;
  metrics: Record<string, unknown> | null;
  error: string | null;
  disclaimer: string;
}
