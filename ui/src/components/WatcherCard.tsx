// Auto-trigger: switch the Gmail watcher on/off and see what it has handled.

import { Alert, Badge, Button, Group, Paper, Stack, Switch, Table, Text } from "@mantine/core";
import { IconRefresh } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

type Message = {
  message_id: string; folder: "inbox" | "spam"; status: "pending" | "done" | "error"; attempts: number;
  error: string | null; classification: string | null; subject: string | null; found_at: string;
};
type Status = {
  enabled: boolean; include_spam: boolean; poll_seconds: number; running: boolean; has_lock: boolean;
  last_check: string | null; next_check: string | null; last_result: { found: number; processed: number } | null;
  last_error: string | null; today: { done: number; errors: number; pending: number } | null; recent: Message[];
};

const STATUS_COLOR = { pending: "gray", done: "green", error: "red" } as const;

function ago(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : new Date(iso).toLocaleString();
}

export function WatcherCard({ connected }: { connected: boolean }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["watcher"], queryFn: () => api.get<Status>("/gmail/watcher"), refetchInterval: 5000 });
  const act = useMutation({
    mutationFn: (action: "on" | "off" | "check") => api.post<Status>(`/gmail/watcher/${action}`),
    onSuccess: (data) => {
      queryClient.setQueryData(["watcher"], data);
      queryClient.invalidateQueries({ queryKey: ["config", "gmail"] });
    },
  });
  const s = status.data;

  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Switch label="Handle new emails automatically" disabled={!connected || !s} checked={!!s?.enabled}
                  onChange={(e) => act.mutate(e.currentTarget.checked ? "on" : "off")} />
          <Group gap="xs">
            {s?.include_spam && <Badge variant="outline" color="orange">Spam included</Badge>}
            <Badge color={s?.enabled && s.has_lock ? "green" : "gray"} variant="light">
              {s?.enabled ? (s.has_lock ? "watching" : "starting") : "off"}
            </Badge>
            <Button size="xs" variant="light" leftSection={<IconRefresh size={14} />} disabled={!connected}
                    loading={act.isPending && act.variables === "check"} onClick={() => act.mutate("check")}>
              Check now
            </Button>
          </Group>
        </Group>
        {!connected && <Text size="sm" c="dimmed">Connect your Google account first.</Text>}
        {s && (
          <Text size="sm" c="dimmed">
            Checks every {s.poll_seconds} s · last check {ago(s.last_check)}
            {s.today && ` · today: ${s.today.done} handled`}
            {s.today?.pending ? `, ${s.today.pending} waiting` : ""}
            {s.today?.errors ? `, ${s.today.errors} failed` : ""}
            {" · "}<Link to="/feedback">see them on the Feedback page</Link>
          </Text>
        )}
        <Text size="xs" c="dimmed">
          Only emails arriving after you switch this on are handled, each once. Nothing is changed in Gmail;
          replies follow the approval mode. Spam (if included below) is reported at most, never answered.
        </Text>
        {s?.last_error && <Alert color="yellow">{s.last_error}</Alert>}
        {act.error && <Alert color="red">{act.error.message}</Alert>}
        {!!s?.recent.length && (
          <Table verticalSpacing={4} fz="xs">
            <Table.Tbody>
              {s.recent.map((m) => (
                <Table.Tr key={m.message_id}>
                  <Table.Td><Badge size="xs" color={STATUS_COLOR[m.status]} variant="light">{m.status}</Badge></Table.Td>
                  <Table.Td>{m.folder === "spam" && <Badge size="xs" color="orange" variant="outline" mr={4}>spam</Badge>}
                    {m.subject ?? m.message_id}</Table.Td>
                  <Table.Td>{m.classification ?? (m.error ? <Text span size="xs" c="red">{m.error}</Text> : "")}</Table.Td>
                  <Table.Td c="dimmed">{ago(m.found_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Paper>
  );
}
