import { Card, PageHeader } from "../components/ui";
import { CoachCard } from "../components/widgets";

export default function MyCoachPage() {
  return (
    <div className="page">
      <PageHeader title="My Coach" subtitle="Academic advising and early-alert support" />
      <div className="detail-grid">
        <div className="detail-main">
          <Card title="What is My Coach?">
            <p>My Coach is the university's academic advising system. It combines your Moodle learning activity with your
              academic record to spot early signs that you may need support, and suggests next steps.</p>
            <ul className="bullets">
              <li><strong>My Coach</strong> is responsible for risk indicators, risk levels, alerts, interventions,
                recommendations and the advising chatbot.</li>
              <li><strong>This LMS</strong> is where you learn: courses, assignments, submissions, quizzes, grades and progress.</li>
            </ul>
            <p className="muted small">The summary on this page is provided by My Coach for your own account only. Open My Coach
              to see the details, the evidence behind each indicator and what to do next. You may be asked to sign in to My Coach.</p>
          </Card>
        </div>
        <aside className="detail-side">
          <CoachCard />
        </aside>
      </div>
    </div>
  );
}
