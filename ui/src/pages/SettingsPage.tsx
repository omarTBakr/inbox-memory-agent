import { Tabs, Title } from "@mantine/core";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { Guide } from "../components/Guide";
import { CalendarStep } from "./setup/CalendarStep";
import { EmbeddingsStep } from "./setup/EmbeddingsStep";
import { GmailStep } from "./setup/GmailStep";
import { ModelStep } from "./setup/ModelStep";
import { NotificationsStep } from "./setup/NotificationsStep";
import { SectionStep } from "./setup/SectionStep";

const TABS = [
  { id: "profile", label: "Profile", view: <SectionStep section="profile" /> },
  { id: "notifications", label: "Notifications", view: <NotificationsStep /> },
  { id: "gmail", label: "Gmail", view: <GmailStep /> },
  { id: "calendar", label: "Calendar", view: <CalendarStep /> },
  { id: "model", label: "Model", view: <ModelStep /> },
  { id: "embeddings", label: "Embeddings", view: <EmbeddingsStep /> },
];

export function SettingsPage() {
  const { section } = useParams();
  const navigate = useNavigate();
  if (!section) return <Navigate to={`/settings/${TABS[0].id}`} replace />;
  return (
    <>
      <Title order={2} mb="md">Settings</Title>
      <Tabs value={section} onChange={(v) => v && navigate(`/settings/${v}`)} keepMounted={false}>
        <Tabs.List mb="lg">
          {TABS.map((t) => <Tabs.Tab key={t.id} value={t.id}>{t.label}</Tabs.Tab>)}
        </Tabs.List>
        {TABS.map((t) => (
          <Tabs.Panel key={t.id} value={t.id}>
            <Guide step={t.id} />
            {t.view}
          </Tabs.Panel>
        ))}
      </Tabs>
    </>
  );
}
