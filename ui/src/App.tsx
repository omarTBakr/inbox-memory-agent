import { Alert, AppShell, Burger, Button, Container, Group, NavLink, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconBrain, IconChartBar, IconMail, IconMessageCircle, IconRocket, IconSettings } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { FeedbackPage } from "./pages/FeedbackPage";
import { MemoryPage } from "./pages/MemoryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { VisualizationsPage } from "./pages/VisualizationsPage";
import { SetupPage, type SetupStatus } from "./pages/SetupPage";
import { confirmLeave } from "./unsaved";

const NAV = [
  { to: "/setup", label: "Setup", icon: IconRocket },
  { to: "/feedback", label: "Feedback", icon: IconMessageCircle },
  { to: "/memory", label: "Memory", icon: IconBrain },
  { to: "/visualizations", label: "Visualizations", icon: IconChartBar },
  { to: "/settings", label: "Settings", icon: IconSettings },
];

// "/" opens the first unfinished setup step, or Feedback once setup is done
function Home() {
  const status = useQuery({ queryKey: ["setup-status"], queryFn: () => api.get<SetupStatus>("/setup/status") });
  if (status.isLoading) return null;
  const todo = status.data?.order.find((s) => s !== "review" && !status.data!.steps[s]?.done);
  return <Navigate to={!status.data ? "/setup" : todo ? `/setup/${todo}` : "/feedback"} replace />;
}

function NotFound() {
  return (
    <Alert color="yellow" title="Page not found">
      <Button component={Link} to="/" variant="light" mt="xs">Go to the start</Button>
    </Alert>
  );
}

export function App() {
  const location = useLocation();
  const [opened, { toggle, close }] = useDisclosure();
  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 200, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="lg">
      <AppShell.Header>
        <Group h="100%" px="md" gap="xs">
          <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
          <IconMail size={22} />
          <Title order={4}>Inbox Memory Agent</Title>
          <Text size="sm" c="dimmed" visibleFrom="sm">long-term memory · LangGraph</Text>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs" component="nav" aria-label="Main">
        {NAV.map((n) => (
          <NavLink key={n.to} component={Link} to={n.to} label={n.label} leftSection={<n.icon size={18} />}
                   active={location.pathname.startsWith(n.to)}
                   onClick={(e) => (confirmLeave() ? close() : e.preventDefault())} />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Container size="xl" px={0}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/setup/:step?" element={<SetupPage />} />
          <Route path="/feedback" element={<FeedbackPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/visualizations" element={<VisualizationsPage />} />
          <Route path="/settings/:section?" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
