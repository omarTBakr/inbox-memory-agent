import { Badge, Group, Stack, Text } from "@mantine/core";
import type { Check } from "../api";

export function CheckList({ checks }: { checks: Record<string, Check> }) {
  return (
    <Stack gap={6}>
      {Object.entries(checks).map(([name, c]) => (
        <Group key={name} gap="sm" wrap="nowrap" align="flex-start">
          <Badge color={c.ok ? "green" : "red"} w={70}>{c.ok ? "OK" : "FAIL"}</Badge>
          <Text fw={500} w={150}>{name.replace(/_/g, " ")}</Text>
          <Text size="sm" c="dimmed" style={{ flex: 1, wordBreak: "break-word" }}>
            {c.detail}{c.ms !== undefined ? ` · ${c.ms} ms` : ""}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}
