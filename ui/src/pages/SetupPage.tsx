import { Button, Group, Loader, Paper, Stepper, Title } from "@mantine/core";
import { IconCheck } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Guide } from "../components/Guide";
import { CalendarStep } from "./setup/CalendarStep";
import { EmbeddingsStep } from "./setup/EmbeddingsStep";
import { GmailStep } from "./setup/GmailStep";
import { HealthStep } from "./setup/HealthStep";
import { ModelStep } from "./setup/ModelStep";
import { NotificationsStep } from "./setup/NotificationsStep";
import { ReviewStep } from "./setup/ReviewStep";
import { SectionStep } from "./setup/SectionStep";

export type SetupStatus = { order: string[]; steps: Record<string, { done: boolean; [k: string]: unknown }> };

// step id (from the backend's order) -> title and page
const STEP_VIEWS: Record<string, { title: string; render: (status?: SetupStatus) => ReactNode }> = {
  health: { title: "System", render: () => <HealthStep /> },
  profile: { title: "Profile", render: () => <SectionStep section="profile" /> },
  notifications: { title: "Notifications", render: () => <NotificationsStep /> },
  gmail: { title: "Gmail", render: () => <GmailStep /> },
  calendar: { title: "Calendar", render: () => <CalendarStep /> },
  model: { title: "Model", render: () => <ModelStep /> },
  embeddings: { title: "Embeddings", render: () => <EmbeddingsStep /> },
  review: { title: "Review", render: (status) => <ReviewStep status={status} /> },
};

export function SetupPage() {
  const { step } = useParams();
  const navigate = useNavigate();
  const status = useQuery({ queryKey: ["setup-status"], queryFn: () => api.get<SetupStatus>("/setup/status") });
  if (!status.data) return <Loader />;

  const order = status.data.order.filter((s) => STEP_VIEWS[s]);
  if (!step || !order.includes(step)) return <Navigate to={`/setup/${order[0]}`} replace />;
  const active = order.indexOf(step);
  const go = (i: number) => navigate(`/setup/${order[i]}`);

  return (
    <>
      <Title order={2} mb="md">Setup</Title>
      <Stepper active={active} onStepClick={go} size="sm" mb="lg" allowNextStepsSelect>
        {order.map((s, i) => {
          // Mantine treats every step before the active one as completed; show real status instead
          const done = !!status.data.steps[s]?.done;
          return (
            <Stepper.Step key={s} label={STEP_VIEWS[s].title} description={done ? "done" : "to do"}
                          color={done ? "green" : "gray"}
                          icon={done ? <IconCheck size={16} /> : i + 1}
                          completedIcon={done ? <IconCheck size={16} /> : i + 1} />
          );
        })}
      </Stepper>
      <Paper withBorder p="lg" radius="md">
        <Title order={3} mb="md">{STEP_VIEWS[step].title}</Title>
        <Guide step={step} />
        {STEP_VIEWS[step].render(status.data)}
      </Paper>
      <Group justify="space-between" mt="md">
        <Button variant="default" disabled={active === 0} onClick={() => go(active - 1)}>Back</Button>
        <Button disabled={active === order.length - 1} onClick={() => go(active + 1)}>Next</Button>
      </Group>
    </>
  );
}
