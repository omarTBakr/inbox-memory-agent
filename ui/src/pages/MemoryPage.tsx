// Long-term memory the assistant has built up, one tab per kind:
// facts (semantic), labelled examples (episodic) and rules (procedural, with every version and what changed).

import { Alert, Badge, Button, Collapse, Group, Loader, Paper, Stack, Tabs, Text, Timeline, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowBackUp, IconBook, IconHistory, IconListCheck, IconMailCheck } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { DiffText } from "../components/DiffText";
import { humanize } from "../components/SchemaForm";
import { ExamplesTab, FactsTab } from "./memory/MemoryBrowser";

type Procedure = {
  name: string;
  prompt: string;
  profile_prompt: string;
  version: number | null;
  updated_at: string | null;
  feedback: string | null;
};
type Version = { version: number; commit_message: string | null; created_at: string | null; text: string };
type History = { name: string; profile_prompt: string; versions: Version[]; note?: string };

const ROLE: Record<string, string> = {
  triage_ignore: "Emails to ignore",
  triage_notify: "Emails to notify you about",
  triage_respond: "Emails to answer",
  agent_instructions: "How replies are written",
};

// commit messages are "v3: <feedback>"
const feedbackOf = (v: Version) => v.commit_message?.replace(/^v\d+:\s*/, "") || "—";

function ProcedureHistory({ name }: { name: string }) {
  const history = useQuery({ queryKey: ["procedure-history", name], queryFn: () => api.get<History>(`/memory/procedures/${name}/history`) });
  if (history.isLoading) return <Loader size="sm" />;
  if (history.error) return <Alert color="red">Could not load the history: {history.error.message}</Alert>;
  const { versions, profile_prompt, note } = history.data!;
  if (note) return <Text size="sm" c="dimmed">{note}</Text>;
  return (
    <Timeline bulletSize={22} lineWidth={2} mt="sm">
      {versions.map((v, i) => {
        const previous = versions[i + 1]?.text ?? profile_prompt;
        return (
          <Timeline.Item key={v.version} bullet={<Text size="xs">{v.version}</Text>}
                         title={<Group gap="xs"><Text size="sm" fw={600}>Version {v.version}</Text>
                           {v.created_at && <Text size="xs" c="dimmed">{new Date(v.created_at).toLocaleString()}</Text>}</Group>}>
            <Text size="xs" c="dimmed" mb={4}>Your feedback: “{feedbackOf(v)}”</Text>
            <Paper withBorder p="xs"><DiffText before={previous} after={v.text} /></Paper>
          </Timeline.Item>
        );
      })}
      <Timeline.Item bullet={<Text size="xs">0</Text>} title={<Text size="sm" fw={600}>From your profile</Text>}>
        <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>{profile_prompt}</Text>
      </Timeline.Item>
    </Timeline>
  );
}

function ProcedureCard({ p }: { p: Procedure }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const reset = useMutation({
    mutationFn: () => api.del(`/memory/procedural/${p.name}`),
    onSuccess: () => {
      notifications.show({ color: "green", message: `${ROLE[p.name] ?? p.name}: back to your profile's text` });
      queryClient.invalidateQueries({ queryKey: ["procedures"] });
    },
    onError: (e) => notifications.show({ color: "red", title: "Not reset", message: e.message }),
  });
  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <div>
          <Title order={4}>{ROLE[p.name] ?? humanize(p.name)}</Title>
          <Text size="xs" c="dimmed">{p.name}</Text>
        </div>
        <Group gap="xs" wrap="nowrap">
          {p.version ? (
            <Badge variant="light" color="violet">v{p.version} · learned</Badge>
          ) : (
            <Badge variant="light" color="gray">from profile</Badge>
          )}
          {p.version && (
            <Button size="compact-xs" variant="subtle" leftSection={<IconHistory size={14} />}
                    aria-expanded={open} onClick={() => setOpen((o) => !o)}>
              {open ? "Hide history" : "History"}
            </Button>
          )}
          {p.version && (
            <Button size="compact-xs" variant="subtle" color="red" leftSection={<IconArrowBackUp size={14} />} loading={reset.isPending}
                    onClick={() => window.confirm("Reset this rule to your profile's text? The learned version stays in the history in Langfuse.") && reset.mutate()}>
              Reset to profile
            </Button>
          )}
        </Group>
      </Group>
      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{p.prompt}</Text>
      {p.version && (
        <Text size="xs" c="dimmed" mt="xs">
          Last changed {p.updated_at ? new Date(p.updated_at).toLocaleString() : ""} after: “{p.feedback}”
        </Text>
      )}
      <Collapse expanded={open}>{open && <ProcedureHistory name={p.name} />}</Collapse>
    </Paper>
  );
}

function RulesTab() {
  const procedures = useQuery({ queryKey: ["procedures"], queryFn: () => api.get<Procedure[]>("/memory/procedures") });
  return (
    <Stack>
      <Text c="dimmed" size="sm">
        Procedures are the rules the assistant follows. They start from your profile and are rewritten when you
        explain on Telegram or on the Feedback page what it should do differently.
      </Text>
      {procedures.isLoading && <Loader />}
      {procedures.error && (
        <Alert color="red" title="Could not load the procedures">
          {procedures.error.message}
          <Group mt="sm"><Button size="xs" variant="light" loading={procedures.isFetching} onClick={() => procedures.refetch()}>Retry</Button></Group>
        </Alert>
      )}
      {procedures.data?.map((p) => <ProcedureCard key={p.name} p={p} />)}
    </Stack>
  );
}

const TABS = ["facts", "examples", "rules"] as const;

export function MemoryPage() {
  // the open tab lives in the URL (?tab=examples) so it can be linked and survives reloads
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t === params.get("tab")) ?? "facts";
  return (
    <Stack>
      <Title order={2}>Memory</Title>
      <Tabs value={tab} onChange={(v) => v && setParams({ tab: v }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="facts" leftSection={<IconBook size={16} />}>Facts</Tabs.Tab>
          <Tabs.Tab value="examples" leftSection={<IconMailCheck size={16} />}>Labelled examples</Tabs.Tab>
          <Tabs.Tab value="rules" leftSection={<IconListCheck size={16} />}>Rules</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="facts">
          <Text c="dimmed" size="sm" mb="sm">What the assistant knows about people, projects and your preferences (semantic memory). It uses them when writing replies.</Text>
          <FactsTab />
        </Tabs.Panel>
        <Tabs.Panel value="examples">
          <Text c="dimmed" size="sm" mb="sm">Emails with the label they should get (episodic memory). The most similar ones are shown to the assistant when it triages a new email.</Text>
          <ExamplesTab />
        </Tabs.Panel>
        <Tabs.Panel value="rules"><RulesTab /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
