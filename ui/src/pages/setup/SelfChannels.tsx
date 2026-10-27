// Login panel for the telegram_self channel: your own account posts into Saved Messages.

import { Alert, Badge, Button, Group, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api";

type TelegramStatus = { connected: boolean; name?: string; username?: string; detail?: string; needs_password?: boolean };

export function TelegramSelfPanel({ save }: { save: () => Promise<void> }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["telegram-self"], queryFn: () => api.get<TelegramStatus>("/notifications/telegram-self/status") });
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["telegram-self"] });

  const sendCode = useMutation({
    mutationFn: async () => {
      await save(); // api_id / api_hash / phone must be stored first
      return api.post("/notifications/telegram-self/send-code");
    },
    onSuccess: () => setCodeSent(true),
  });
  const verify = useMutation({
    mutationFn: () => api.post<TelegramStatus>("/notifications/telegram-self/verify", { code, password }),
    onSuccess: (r) => {
      setNeedsPassword(!!r.needs_password);
      if (r.connected) {
        setCodeSent(false);
        refresh();
      }
    },
  });
  const logout = useMutation({ mutationFn: () => api.post("/notifications/telegram-self/logout"), onSuccess: refresh });
  const s = status.data;

  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={5}>Telegram · Saved Messages (your account)</Title>
          {s && <Badge color={s.connected ? "green" : "gray"}>{s.connected ? `logged in as ${s.name}` : "not logged in"}</Badge>}
        </Group>
        <Text size="sm" c="dimmed">
          Get api_id and api_hash at my.telegram.org → API development tools, fill them in above with your phone,
          then request a code: Telegram sends it to your app. Messages land in Saved Messages (no phone alert).
        </Text>
        {s?.detail && <Alert color="yellow">{s.detail}</Alert>}
        <Group align="flex-end">
          <Button variant="light" loading={sendCode.isPending} onClick={() => sendCode.mutate()}>
            {s?.connected ? "Log in again" : "Send login code"}
          </Button>
          {s?.connected && <Button variant="subtle" color="red" onClick={() => logout.mutate()}>Log out</Button>}
        </Group>
        {codeSent && (
          <Group align="flex-end">
            <TextInput label="Code from Telegram" value={code} onChange={(e) => setCode(e.currentTarget.value)} w={180} />
            {needsPassword && (
              <PasswordInput label="Two-step verification password" value={password}
                             onChange={(e) => setPassword(e.currentTarget.value)} w={260} />
            )}
            <Button loading={verify.isPending} disabled={!code} onClick={() => verify.mutate()}>Log in</Button>
          </Group>
        )}
        {needsPassword && <Alert color="blue">Your account has two-step verification: enter its password and log in again.</Alert>}
        {(sendCode.error || verify.error) && <Alert color="red">{String((sendCode.error ?? verify.error)?.message)}</Alert>}
      </Stack>
    </Paper>
  );
}
