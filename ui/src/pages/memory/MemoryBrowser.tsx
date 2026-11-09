// Facts (semantic memory) and labelled examples (episodic memory): list, search, forget.
// Search ranks by embedding similarity; without a search the newest come first.

import { ActionIcon, Alert, Badge, Button, Group, Loader, Paper, Stack, Table, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconSearch, IconTrash } from "@tabler/icons-react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "../../api";

type Kind = "semantic" | "episodic";
export type MemoryItem<V> = { key: string; value: V; created_at: string | null; updated_at: string | null; score: number | null };
type Page<V> = { items: MemoryItem<V>[]; has_more: boolean };

const PAGE = 50;
const LABEL_COLOR: Record<string, string> = { ignore: "gray", notify: "blue", respond: "green" };
const SOURCE: Record<string, string> = {
  "feedback:up": "👍 confirmed",
  "feedback:label": "label corrected",
  cli: "make feedback",
};

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

function useMemories<V>(kind: Kind, query: string) {
  return useInfiniteQuery({
    queryKey: ["memory", kind, query],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE), offset: String(pageParam) });
      if (query) params.set("q", query);
      return api.get<Page<V>>(`/memory/${kind}?${params}`);
    },
    getNextPageParam: (last, pages) => (last.has_more ? pages.length * PAGE : undefined),
  });
}

function useForget(kind: Kind, what: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => api.del(`/memory/${kind}/${encodeURIComponent(key)}`),
    onSuccess: () => {
      notifications.show({ color: "green", message: `${what} forgotten` });
      queryClient.invalidateQueries({ queryKey: ["memory", kind] });
    },
    onError: (e) => notifications.show({ color: "red", title: `${what} not deleted`, message: e.message }),
  });
}

function Browser<V>({ kind, placeholder, empty, render }: {
  kind: Kind;
  placeholder: string;
  empty: ReactNode;
  render: (items: MemoryItem<V>[], searching: boolean) => ReactNode;
}) {
  const [search, setSearch] = useState("");
  const [query] = useDebouncedValue(search.trim(), 400);
  const list = useMemories<V>(kind, query);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Stack>
      <TextInput leftSection={<IconSearch size={16} />} placeholder={placeholder} aria-label="Search memories"
                 value={search} onChange={(e) => setSearch(e.currentTarget.value)}
                 rightSection={list.isFetching && !list.isFetchingNextPage ? <Loader size="xs" /> : null} />
      {query && <Text size="xs" c="dimmed">Ranked by meaning, closest first. The match score is shown on each item.</Text>}
      {list.isLoading && <Loader />}
      {list.error && (
        <Alert color="red" title="Could not load memories">
          {list.error.message}
          <Group mt="sm"><Button size="xs" variant="light" onClick={() => list.refetch()}>Retry</Button></Group>
        </Alert>
      )}
      {list.data && items.length === 0 && (query ? <Text c="dimmed">Nothing matches “{query}”.</Text> : <Alert>{empty}</Alert>)}
      {items.length > 0 && render(items, !!query)}
      {list.hasNextPage && (
        <Group><Button variant="default" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button></Group>
      )}
    </Stack>
  );
}

function ForgetButton({ label, busy, onConfirm }: { label: string; busy: boolean; onConfirm: () => void }) {
  return (
    <Tooltip label="Forget">
      <ActionIcon variant="subtle" color="red" aria-label={`Forget ${label}`} loading={busy}
                  onClick={() => window.confirm(`Forget ${label}? This cannot be undone.`) && onConfirm()}>
        <IconTrash size={16} />
      </ActionIcon>
    </Tooltip>
  );
}

const Score = ({ score }: { score: number | null }) =>
  score === null ? null : <Badge size="xs" variant="outline" color="gray">match {Math.round(score * 100)}%</Badge>;

type Fact = { content: string | Record<string, unknown> };

export function FactsTab() {
  const forget = useForget("semantic", "Fact");
  return (
    <Browser<Fact>
      kind="semantic"
      placeholder="Search facts, e.g. “who handles invoices?”"
      empty="No facts yet. The assistant saves facts about people, projects and preferences while it answers emails."
      render={(items, searching) => (
        <Stack gap="xs">
          {items.map((m) => {
            const text = typeof m.value.content === "string" ? m.value.content : JSON.stringify(m.value.content);
            return (
              <Paper key={m.key} withBorder p="sm">
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <Stack gap={4}>
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{text}</Text>
                    <Group gap="xs">
                      <Text size="xs" c="dimmed">Saved {when(m.created_at)}</Text>
                      {m.updated_at !== m.created_at && <Text size="xs" c="dimmed">· updated {when(m.updated_at)}</Text>}
                      {searching && <Score score={m.score} />}
                    </Group>
                  </Stack>
                  <ForgetButton label="this fact" busy={forget.isPending && forget.variables === m.key}
                                onConfirm={() => forget.mutate(m.key)} />
                </Group>
              </Paper>
            );
          })}
        </Stack>
      )}
    />
  );
}

type Example = {
  email: { author: string; to: string; subject: string; email_thread: string };
  label: string;
  source?: string;
  recorded_at?: string;
};

export function ExamplesTab() {
  const forget = useForget("episodic", "Example");
  return (
    <Browser<Example>
      kind="episodic"
      placeholder="Search examples by sender, subject or content"
      empty="No labelled examples yet. Confirm (👍) or correct a label on Telegram or the Feedback page: similar emails then follow it."
      render={(items, searching) => (
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr><Table.Th>Email</Table.Th><Table.Th>Should be</Table.Th><Table.Th>Learned from</Table.Th><Table.Th>Recorded</Table.Th><Table.Th /></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((m) => (
                <Table.Tr key={m.key}>
                  <Table.Td maw={380}>
                    <Tooltip label={m.value.email.email_thread.slice(0, 400)} multiline w={420}>
                      <Text size="sm" fw={500} lineClamp={1}>{m.value.email.subject}</Text>
                    </Tooltip>
                    <Text size="xs" c="dimmed" lineClamp={1}>{m.value.email.author}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Badge variant="light" color={LABEL_COLOR[m.value.label]}>{m.value.label}</Badge>
                      {searching && <Score score={m.score} />}
                    </Group>
                  </Table.Td>
                  <Table.Td><Text size="xs">{SOURCE[m.value.source ?? ""] ?? m.value.source ?? "—"}</Text></Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{when(m.value.recorded_at ?? m.created_at)}</Text></Table.Td>
                  <Table.Td>
                    <ForgetButton label={`the example “${m.value.email.subject}”`}
                                  busy={forget.isPending && forget.variables === m.key} onConfirm={() => forget.mutate(m.key)} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    />
  );
}
