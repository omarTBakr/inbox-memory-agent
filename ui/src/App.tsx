import { AppShell, Container, Group, NavLink, Text, Title } from "@mantine/core";
import { IconChartBar, IconMail, IconMessageCircle, IconRocket, IconSettings } from "@tabler/icons-react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { FeedbackPage } from "./pages/FeedbackPage";
import { SettingsPage } from "./pages/SettingsPage";
import { VisualizationsPage } from "./pages/VisualizationsPage";
import { SetupPage } from "./pages/SetupPage";

const NAV = [
  { to: "/setup", label: "Setup", icon: IconRocket },
  { to: "/feedback", label: "Feedback", icon: IconMessageCircle },
  { to: "/visualizations", label: "Visualizations", icon: IconChartBar },
  { to: "/settings", label: "Settings", icon: IconSettings },
];

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 200, breakpoint: "sm" }} padding="lg">
      <AppShell.Header>
        <Group h="100%" px="md" gap="xs">
          <IconMail size={22} />
          <Title order={4}>Email Assistant</Title>
          <Text size="sm" c="dimmed">long-term memory · LangGraph</Text>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {NAV.map((n) => (
          <NavLink key={n.to} label={n.label} leftSection={<n.icon size={18} />}
                   active={location.pathname.startsWith(n.to)} onClick={() => navigate(n.to)} />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Container size="xl" px={0}>
        <Routes>
          <Route path="/" element={<Navigate to="/setup" replace />} />
          <Route path="/setup/:step?" element={<SetupPage />} />
          <Route path="/feedback" element={<FeedbackPage />} />
          <Route path="/visualizations" element={<VisualizationsPage />} />
          <Route path="/settings/:section?" element={<SettingsPage />} />
        </Routes>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
