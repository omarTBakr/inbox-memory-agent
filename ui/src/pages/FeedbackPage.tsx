// Every email the assistant handled, with its rating and what the feedback changed in memory.
// Rating here has the same effect as the Telegram buttons.

import { ActionIcon, Alert, Badge, Button, Group, Loader, Paper, Stack, Table, Text, Textarea, Title, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconInbox, IconPencil, IconSend, IconThumbDown, IconThumbUp } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { api } from "../api";

type Item = {
  id: string;
  created_at: string;
  stage: string;
  email: { author: string; subject: string; folder?: "inbox" | "spam" };
  classification: string;
  reasoning: string;
  notification: { warnings?: string[] } | null;
  rating: "up" | "down" | null;
  corrected_label: string | null;
  comment: string | null;
  applied: { memory: string; label?: string; name?: string; version?: number }[];
  digest_sent: boolean;
  moved_to_inbox: boolean;
};

const LABELS = ["ignore", "notify", "respond"];
const COLOR: Record<string, string> = { ignore: "gray", notify: "blue", respond: "green" };

function CommentBox({ item, onDone }: { item: Item; onDone: () => void }) {
  const [comment, setComment] = useState("");
  const rate = useMutation({
    mutationFn: () => api.post<{ summary: string }>(`/feedback/${item.id}`, { rating: "comment", comment }),
    onSuccess: (r) => {
      notifications.show({ color: "green", message: r.summary });
      onDone();
    },
  });
  return (
    <Paper withBorder p="sm" bg="var(--mantine-color-default-hover)">
      <Stack gap="xs">
        <Textarea size="sm" placeholder="What should the assistant do differently? (rewrites its instructions)" autosize minRows={2}
                  value={comment} onChange={(e) => setComment(e.currentTarget.value)} />
        <Group>
          <Button size="xs" disabled={!comment} loading={rate.isPending} onClick={() => rate.mutate()}>Apply feedback</Button>
        </Group>
        {rate.error && <Alert color="red">{rate.error.message}</Alert>}
      </Stack>
    </Paper>
  );
}

export function FeedbackPage() {
  const queryClient = useQueryClient();
  const items = useQuery({ queryKey: ["feedback"], queryFn: () => api.get<Item[]>("/feedback?limit=100") });
  const listener = useQuery({ queryKey: ["listener"], queryFn: () => api.get<{ running: boolean; last_error: string | null }>("/feedback/listener"), refetchInterval: 15000 });
  const [open, setOpen] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["feedback"] });
  const up = useMutation({ mutationFn: (id: string) => api.post<{ summary: string }>(`/feedback/${id}`, { rating: "up" }),
                           onSuccess: (r) => { notifications.show({ color: "green", message: r.summary }); refresh(); } });
  const down = useMutation({ mutationFn: (id: string) => api.post<{ summary: string }>(`/feedback/${id}`, { rating: "down" }),
                             onSuccess: (r) => { notifications.show({ message: r.summary }); refresh(); } });
  const label = useMutation({
    mutationFn: ({ id, label }: { id: string; label: string }) => api.post<{ summary: string }>(`/feedback/${id}`, { rating: "label", label }),
    onSuccess: (r) => { notifications.show({ color: "green", message: r.summary }); refresh(); },
  });
  const notSpam = useMutation({
    mutationFn: (id: string) => api.post<{ summary: string }>(`/feedback/${id}`, { rating: "not_spam" }),
    onSuccess: (r) => { notifications.show({ color: "green", message: r.summary }); refresh(); },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });
  const digest = useMutation({
    mutationFn: () => api.post<{ items: number; messages_sent: number }>("/feedback/digest/send"),
    onSuccess: (r) => notifications.show({ message: r.items ? `${r.items} ignored email(s), ${r.messages_sent} message(s) sent` : "No ignored emails waiting" }),
  });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Feedback</Title>
        <Group>
          <Badge color={listener.data?.running ? "green" : "gray"} variant="light">
            Telegram listener {listener.data?.running ? "running" : "off"}
          </Badge>
          <Button variant="light" leftSection={<IconSend size={16} />} loading={digest.isPending} onClick={() => digest.mutate()}>
            Send ignored digest now
          </Button>
        </Group>
      </Group>
      <Text c="dimmed" size="sm">
        Pick the right label (✓ marks the current one) or 👍 to confirm: similar emails follow it (episodic memory).
        ✏️ explains what should change (procedural memory). Same buttons as under each Telegram message.
      </Text>
      {listener.data?.last_error && <Alert color="yellow">Listener: {listener.data.last_error}</Alert>}
      {items.isLoading && <Loader />}
      {items.data?.length === 0 && <Alert>No handled emails yet: run the samples or your Gmail from Setup → Review.</Alert>}
      {items.data && items.data.length > 0 && (
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr><Table.Th>Email</Table.Th><Table.Th>Decision</Table.Th><Table.Th>Feedback</Table.Th><Table.Th>Memory changed</Table.Th></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.data.map((item) => (
              <Fragment key={item.id}>
                <Table.Tr>
                  <Table.Td maw={340}>
                    <Group gap={6} wrap="nowrap">
                      {item.email.folder === "spam" && (
                        <Tooltip label="Found in your Gmail Spam folder: reported at most, never answered">
                          <Badge size="xs" color="orange" variant="outline">{item.moved_to_inbox ? "was spam" : "spam"}</Badge>
                        </Tooltip>
                      )}
                      <Text size="sm" fw={500} lineClamp={1}>{item.email.subject}</Text>
                    </Group>
                    <Text size="xs" c="dimmed" lineClamp={1}>{item.email.author} · {new Date(item.created_at).toLocaleString()}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label={item.reasoning} multiline w={360}>
                      <Badge color={COLOR[item.classification]} variant="light">{item.classification}</Badge>
                    </Tooltip>
                    {item.classification === "ignore" && <Text size="xs" c="dimmed">{item.digest_sent ? "in digest" : "digest pending"}</Text>}
                    {item.notification?.warnings?.map((w) => <Text key={w} size="xs" c="orange">⚠️ {w}</Text>)}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap" mb={4}>
                      {LABELS.map((l) => {
                        const current = (item.corrected_label ?? item.classification) === l;
                        return (
                          <Button key={l} size="compact-xs" color={COLOR[l]} variant={current ? "filled" : "default"}
                                  onClick={() => label.mutate({ id: item.id, label: l })}>
                            {current ? "✓ " : ""}{l}
                          </Button>
                        );
                      })}
                    </Group>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon variant={item.rating === "up" ? "filled" : "subtle"} color="green" aria-label="Thumbs up"
                                  onClick={() => up.mutate(item.id)}><IconThumbUp size={16} /></ActionIcon>
                      <ActionIcon variant={item.rating === "down" ? "filled" : "subtle"} color="red" aria-label="Thumbs down"
                                  onClick={() => down.mutate(item.id)}><IconThumbDown size={16} /></ActionIcon>
                      <Tooltip label="Explain what should change">
                        <ActionIcon variant={open === item.id ? "filled" : "subtle"} aria-label="Written feedback"
                                    onClick={() => setOpen(open === item.id ? null : item.id)}><IconPencil size={16} /></ActionIcon>
                      </Tooltip>
                      {item.email.folder === "spam" && (
                        <Button size="compact-xs" variant="light" leftSection={<IconInbox size={14} />}
                                disabled={item.moved_to_inbox} loading={notSpam.isPending && notSpam.variables === item.id}
                                onClick={() => notSpam.mutate(item.id)}>
                          {item.moved_to_inbox ? "In Inbox" : "Not spam"}
                        </Button>
                      )}
                    </Group>
                    {item.comment && <Text size="xs" c="dimmed" lineClamp={2}>“{item.comment}”</Text>}
                  </Table.Td>
                  <Table.Td>
                    {item.applied.map((a, i) => (
                      <Badge key={i} size="xs" variant="outline" mr={4}>
                        {a.memory}{a.label ? `: ${a.label}` : ""}{a.name ? `: ${a.name} v${a.version}` : ""}
                      </Badge>
                    ))}
                  </Table.Td>
                </Table.Tr>
                {open === item.id && (
                  <Table.Tr>
                    <Table.Td colSpan={4}><CommentBox item={item} onDone={() => { setOpen(null); refresh(); }} /></Table.Td>
                  </Table.Tr>
                )}
              </Fragment>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
