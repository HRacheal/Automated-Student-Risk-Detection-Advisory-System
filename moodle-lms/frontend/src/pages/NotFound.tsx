import { Link } from "react-router-dom";
import { EmptyState, PageHeader } from "../components/ui";

export default function NotFoundPage() {
  return (
    <div className="page">
      <PageHeader title="Page not found" />
      <EmptyState title="This page does not exist." icon="alert"><Link to="/">Go to the dashboard</Link></EmptyState>
    </div>
  );
}
