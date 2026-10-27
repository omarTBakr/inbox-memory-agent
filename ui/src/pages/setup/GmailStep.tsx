import { Alert, Badge, Button, Code, Divider, FileButton, Group, List, Stack, Text } from "@mantine/core";
import { IconBrandGmail, IconPlugConnected, IconUpload } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { SectionEditor } from "../../components/SectionEditor";
import { WatcherCard } from "../../components/WatcherCard";

type Status = { client_configured: boolean; connected: boolean; redirect_url: string; scopes: string[] };
type TestResult = { email: string; messages_total: number; inbox_unread: number };

export function GmailStep() {
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const status = useQuery({ queryKey: ["gmail-status"], queryFn: () => api.get<Status>("/gmail/status") });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["gmail-status"] });
    queryClient.invalidateQueries({ queryKey: ["setup-status"] });
  };

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.post<{ client_type: string }>("/gmail/client", form);
    },
    onSuccess: refresh,
  });
  const connect = useMutation({
    mutationFn: () => api.get<{ url: string }>("/gmail/oauth/start"),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const test = useMutation({ mutationFn: () => api.post<TestResult>("/gmail/test") });
  const disconnect = useMutation({ mutationFn: () => api.post("/gmail/disconnect"), onSuccess: refresh });

  const s = status.data;
  return (
    <Stack>
      {params.get("gmail") === "connected" && <Alert color="green">Google account connected.</Alert>}
      {params.get("gmail") === "error" && <Alert color="red">Google sign-in failed or was cancelled. Try connecting again.</Alert>}

      <Divider label="1 · Google OAuth client" labelPosition="left" />
      <Text size="sm" c="dimmed">
        In Google Cloud Console: enable the Gmail API (and Calendar API if you use it), create an OAuth client
        (Desktop or Web), add this redirect URI, and download the JSON.
      </Text>
      {s && <Code>{s.redirect_url}</Code>}
      <Group>
        <FileButton onChange={(f) => f && upload.mutate(f)} accept="application/json">
          {(props) => (
            <Button {...props} variant="light" leftSection={<IconUpload size={16} />} loading={upload.isPending}>
              Upload client JSON
            </Button>
          )}
        </FileButton>
        {s && <Badge color={s.client_configured ? "green" : "gray"}>{s.client_configured ? "client saved" : "no client yet"}</Badge>}
      </Group>
      {upload.error && <Alert color="red">{String(upload.error.message)}</Alert>}

      <Divider label="2 · Connect your account" labelPosition="left" />
      <Group>
        <Button leftSection={<IconBrandGmail size={16} />} disabled={!s?.client_configured} loading={connect.isPending}
                onClick={() => connect.mutate()}>
          {s?.connected ? "Reconnect Google" : "Connect Google"}
        </Button>
        <Button variant="light" leftSection={<IconPlugConnected size={16} />} disabled={!s?.connected}
                loading={test.isPending} onClick={() => test.mutate()}>
          Test connection
        </Button>
        {s?.connected && <Button variant="subtle" color="red" onClick={() => disconnect.mutate()}>Disconnect</Button>}
        {s && <Badge color={s.connected ? "green" : "gray"}>{s.connected ? "connected" : "not connected"}</Badge>}
      </Group>
      {connect.error && <Alert color="red">{String(connect.error.message)}</Alert>}
      {test.data && (
        <Alert color="green" title={test.data.email}>
          {test.data.inbox_unread} unread in inbox · {test.data.messages_total} messages in total
        </Alert>
      )}
      {test.error && <Alert color="red">{String(test.error.message)}</Alert>}
      {s && (
        <List size="xs" c="dimmed">
          {s.scopes.map((scope) => <List.Item key={scope}>{scope}</List.Item>)}
        </List>
      )}

      <Divider label="3 · How the assistant uses your inbox" labelPosition="left" />
      <SectionEditor section="gmail" onSaved={() => { refresh(); queryClient.invalidateQueries({ queryKey: ["watcher"] }); }} />

      <Divider label="4 · Watch for new mail" labelPosition="left" />
      <WatcherCard connected={!!s?.connected} />
    </Stack>
  );
}
