import { Card, Loaded, PageHeader, Skeleton } from "../components/ui";
import { markRead, NotificationList } from "../components/widgets";
import type { NotificationItem } from "../types";
import { useApi } from "../useApi";

export default function NotificationsPage() {
  const state = useApi<{ notifications: NotificationItem[] }>("/api/notifications");
  const read = async (n: NotificationItem) => {
    await markRead(n);
  };
  return (
    <div className="page">
      <PageHeader title="Notifications"
        subtitle="Moodle notifications and announcements, plus reminders worked out from your real Moodle deadlines, submissions and grades" />
      <Loaded state={state} skeleton={<Skeleton rows={8} />}>
        {(d) => {
          const unread = d.notifications.filter((n) => !n.read);
          const rest = d.notifications.filter((n) => n.read);
          return (
            <div className="stack">
              <Card title={`Needs attention (${unread.length})`}><NotificationList items={unread} onRead={read} /></Card>
              <Card title="Earlier"><NotificationList items={rest} onRead={read} /></Card>
            </div>
          );
        }}
      </Loaded>
    </div>
  );
}
