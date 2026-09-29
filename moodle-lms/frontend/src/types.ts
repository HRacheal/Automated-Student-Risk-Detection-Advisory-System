// Shapes returned by the LMS backend (moodle-lms/backend/lms). Timestamps are Unix seconds.

export interface User {
  fullname: string;
  student_id: string;
  username: string;
  timezone: string;
  mycoach_portal_url: string;
}

export interface Course {
  id: number;
  code: string;
  title: string;
  term: string | null;
  fullname: string;
  summary: string;
  instructors: string[];
  progress: number | null;
  completed: boolean;
  completion_enabled: boolean;
  last_access: number | null;
  start_date: number | null;
  end_date: number | null;
}

export interface DeadlineItem {
  kind: "assignment" | "quiz";
  cmid: number;
  name: string;
  course_code: string;
  course_id: number;
  due: number;
  opens?: number | null;
  cutoff?: number | null;
  state: string;
  link: string;
}

export interface ActivityEvent {
  type: string;
  title: string;
  course_code: string | null;
  activity: string | null;
  timestamp: number;
  status: string | null;
  link: string | null;
}

export interface NotificationItem {
  id: string;
  moodle_id?: number;
  source: "moodle" | "reminder";
  type: string;
  title: string;
  body: string;
  course_code: string | null;
  timestamp: number | null;
  read: boolean;
  link: string | null;
}

export interface CourseCard extends Course {
  completed_activities: number;
  tracked_activities: number;
  next_activity: DeadlineItem | null;
  last_activity: ActivityEvent | null;
}

export interface Dashboard {
  courses: CourseCard[];
  upcoming: DeadlineItem[];
  overdue: DeadlineItem[];
  recent_activity: ActivityEvent[];
  notifications: NotificationItem[];
  unread_notifications: number;
  progress: { completed: number; tracked: number; average_course_progress: number | null };
}

export interface AssignmentSummary {
  cmid: number;
  id: number;
  course_id: number;
  course_code: string;
  name: string;
  due_date: number | null;
  extension_due_date: number | null;
  cutoff_date: number | null;
  opens: number | null;
  max_grade: number | null;
  state: "submitted" | "draft" | "closed" | "overdue" | "not_open" | "open";
  submission_status: string;
  submitted_at: number | null;
  late: boolean;
  late_by_seconds: number | null;
  grading_status: string | null;
  graded: boolean;
  grade: string | null;
  graded_at: number | null;
  feedback: string[];
  can_edit: boolean;
  can_submit_for_grading: boolean;
  requires_submit_for_grading: boolean;
  submissions_enabled: boolean;
  locked: boolean;
}

export interface FileLink {
  filename: string;
  size?: number | null;
  mimetype?: string | null;
  modified?: number | null;
  url: string | null;
}

export interface AssignmentDetail extends AssignmentSummary {
  course_title: string;
  description: string;
  attachments: FileLink[];
  file_submissions: boolean;
  max_files: number | null;
  max_bytes: number | null;
  accepted_types: string | null;
  online_text: boolean;
  submitted_files: FileLink[];
  submitted_text: string;
  submission_created: number | null;
  submission_modified: number | null;
  staged_files: { filename: string; size: number }[];
  grading_due_date: number | null;
}

export interface QuizSummary {
  cmid: number;
  id: number;
  course_id: number;
  course_code: string;
  name: string;
  opens: number | null;
  closes: number | null;
  time_limit: number | null;
  attempts_allowed: number | null;
  attempts_used: number;
  max_grade: number | null;
  grade: number | null;
  state: "in_progress" | "not_open" | "closed" | "completed" | "attempted" | "open";
  in_progress_attempt: number | null;
  last_finished: number | null;
}

export interface QuizDetail extends QuizSummary {
  course_title: string;
  description: string;
  grade_method: string | null;
  rules: string[];
  can_attempt: boolean;
  can_review: boolean;
  prevent_access: string[];
  prevent_new_attempt: string[];
  overall_feedback: string;
  attempts: { id: number; number: number; state: string; started: number | null; finished: number | null; grade: number | null }[];
}

export type QuestionField =
  | { kind: "radio"; name: string; options: { value: string; label: string }[]; value: string | null }
  | { kind: "checkbox"; name: string; label: string; value: string; checked: boolean }
  | { kind: "text" | "textarea"; name: string; label: string; value: string }
  | { kind: "select"; name: string; label: string; options: { value: string; label: string }[]; value: string };

export interface Question {
  slot: number;
  page: number;
  number: string | number | null;
  type: string;
  status: string;
  state_class: string | null;
  mark: string | null;
  max_mark: number | null;
  text: string;
  fields: QuestionField[];
  readonly: boolean;
  supported: boolean;
  feedback: { specific?: string; general?: string; right_answer?: string; outcome?: string };
}

export interface AttemptPage {
  attempt_id: number;
  quiz_cmid: number;
  quiz_name: string;
  course_code: string;
  state: string;
  page: number;
  pages: number;
  next_page: number;
  time_limit: number | null;
  started: number | null;
  messages: string[];
  questions: Question[];
}

export interface AttemptReview {
  attempt_id: number;
  quiz_cmid: number;
  quiz_name: string;
  course_code: string;
  state: string;
  started: number | null;
  finished: number | null;
  grade: number | null;
  max_grade: number | null;
  additional: { title: string; content: string }[];
  questions: Question[];
}

export interface GradeItem {
  id: number;
  name: string | null;
  type: string;
  module: string | null;
  cmid: number | null;
  grade: number | null;
  grade_formatted: string | null;
  grade_max: number | null;
  grade_min: number | null;
  percentage: string | null;
  range: string | null;
  weight: string | null;
  graded_at: number | null;
  hidden: boolean;
  feedback: string;
}

export interface CourseGrades {
  course_id: number;
  course_code: string;
  course_title: string;
  items: GradeItem[];
  course_total: GradeItem | null;
  progress: number | null;
}

export interface ProgressActivity {
  cmid: number;
  name: string;
  module: string;
  section: string;
  tracked: boolean;
  completed: boolean | null;
  completed_at: number | null;
  rules: string[];
}

export interface CourseProgress {
  course_id: number;
  course_code: string;
  course_title: string;
  completion_enabled: boolean;
  percentage: number | null;
  completed: number;
  tracked: number;
  remaining: number;
  by_type: Record<string, { total: number; completed: number }>;
  last_access: number | null;
  activities: ProgressActivity[];
}

export interface Module {
  cmid: number;
  name: string;
  module: string;
  module_label: string;
  description: string;
  dates: { label: string; timestamp: number }[];
  completion: { tracked: boolean; completed: boolean | null; manual: boolean };
  moodle_url: string | null;
  files: FileLink[];
  assignment?: AssignmentSummary;
  quiz?: QuizSummary;
}

export interface CourseDetail extends Course {
  sections: { id: number; number: number; name: string; summary: string; modules: Module[] }[];
  assignments: AssignmentSummary[];
  quizzes: QuizSummary[];
  progress_detail: CourseProgress;
}

export interface CalendarEvent {
  id: number;
  name: string;
  description: string;
  course_id: number | null;
  course_code: string | null;
  module: string | null;
  event_type: string;
  start: number;
  duration: number;
  link: string | null;
}

export interface Profile {
  fullname: string;
  student_id: string;
  username: string;
  email: string | null;
  department: string | null;
  institution: string | null;
  first_access: number | null;
  last_access: number | null;
  program: string | null;
  courses: { id: number; code: string; title: string; term: string | null }[];
}

export interface CoachSummary {
  available: boolean;
  portal_url: string;
  message?: string;
  student_id?: string;
  risk_level?: "LOW" | "MODERATE" | "HIGH" | null;
  last_synced_at?: string;
  open_indicators?: number;
  indicators?: { title: string; severity: string }[];
}
