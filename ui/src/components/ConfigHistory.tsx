// Saved versions of one config section, newest first, each with the fields it changed.
// "Load into form" copies an old version into the editor as unsaved edits; Save makes it current.

import { Alert, Badge, Button, Code, Drawer, Group, Loader, Paper, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { changedFields } from "../diff";

type Version = { version: number; data: Record<string, any>; saved_at: string };

const show = (v: unknown) =>
  v === undefined ? "(not set)" : v === "" || v === null ? "(empty)" : typeof v === "string" ? v : JSON.stringify(v);

type Props = {
  section: string;
  opened: boolean;
  onClose: () => void;
  current?: number;
  onLoad: (data: Record<string, any>) => void;
};

export function ConfigHistory({ section, opened, onClose, current, onLoad }: Props) {
  const history = useQuery({
    queryKey: ["config-history", section, current],
    queryFn: () => api.get<Version[]>(`/config/${section}/history`),
    enabled: opened,
  });
  const rows = history.data ?? [];

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="lg" title={`History of ${section}`}>
      {history.isLoading && <Loader />}
      {history.error && <Alert color="red">Could not load the history: {history.error.message}</Alert>}
      {history.data && rows.length === 0 && <Text c="dimmed">Never saved: the values come from the defaults.</Text>}
      <Stack>
        {rows.map((v, i) => {
          const previous = rows[i + 1];
          const changes = previous ? changedFields(previous.data, v.data) : [];
          return (
            <Paper key={v.version} withBorder p="sm">
              <Group justify="space-between" mb="xs">
                <Group gap="xs">
                  <Badge variant="light" color={v.version === current ? "green" : "gray"}>v{v.version}</Badge>
                  {v.version === current && <Text size="xs" c="green">current</Text>}
                  <Text size="xs" c="dimmed">{new Date(v.saved_at).toLocaleString()}</Text>
                </Group>
                {v.version !== current && (
                  <Button size="compact-xs" variant="light" onClick={() => { onLoad(v.data); onClose(); }}>
                    Load into form
                  </Button>
                )}
              </Group>
              {!previous ? (
                <Text size="xs" c="dimmed">First saved version.</Text>
              ) : changes.length === 0 ? (
                <Text size="xs" c="dimmed">Saved again without changes.</Text>
              ) : (
                <Table.ScrollContainer minWidth={420}>
                  <Table fz="xs" verticalSpacing={4}>
                    <Table.Thead>
                      <Table.Tr><Table.Th>Field</Table.Th><Table.Th>Before</Table.Th><Table.Th>After</Table.Th></Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {changes.map((c) => (
                        <Table.Tr key={c.path}>
                          <Table.Td><Code>{c.path}</Code></Table.Td>
                          <Table.Td c="red">{show(c.before)}</Table.Td>
                          <Table.Td c="green">{show(c.after)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </Paper>
          );
        })}
      </Stack>
    </Drawer>
  );
}
