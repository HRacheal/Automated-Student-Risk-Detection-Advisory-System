import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { ErrorState, Loading } from "./components/ui";
import ActivityPage from "./pages/Activity";
import AssignmentDetailPage from "./pages/AssignmentDetail";
import AssignmentsPage from "./pages/Assignments";
import CalendarPage from "./pages/Calendar";
import CourseDetailPage from "./pages/CourseDetail";
import CoursesPage from "./pages/Courses";
import DashboardPage from "./pages/Dashboard";
import GradesPage from "./pages/Grades";
import LoginPage from "./pages/Login";
import MyCoachPage from "./pages/MyCoach";
import NotFoundPage from "./pages/NotFound";
import NotificationsPage from "./pages/Notifications";
import ProfilePage from "./pages/Profile";
import ProgressPage from "./pages/Progress";
import QuizAttemptPage from "./pages/QuizAttempt";
import QuizDetailPage from "./pages/QuizDetail";
import QuizReviewPage from "./pages/QuizReview";
import QuizzesPage from "./pages/Quizzes";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking, bootError, retry } = useAuth();
  const location = useLocation();
  if (checking) return <div className="boot"><Loading label="Starting My Coach LMS…" /></div>;
  if (bootError) return <div className="boot"><ErrorState error={bootError} onRetry={retry} /></div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="courses" element={<CoursesPage />} />
        <Route path="courses/:courseId" element={<CourseDetailPage />} />
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="assignments/:cmid" element={<AssignmentDetailPage />} />
        <Route path="quizzes" element={<QuizzesPage />} />
        <Route path="quizzes/:cmid" element={<QuizDetailPage />} />
        <Route path="quiz-attempts/:attemptId" element={<QuizAttemptPage />} />
        <Route path="quiz-attempts/:attemptId/review" element={<QuizReviewPage />} />
        <Route path="grades" element={<GradesPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="my-coach" element={<MyCoachPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
