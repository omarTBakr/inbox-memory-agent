import { Alert, Badge, Button, Group, Loader, NumberInput, Stack, Table, Text } from "@mantine/core";
import { IconBrandGmail, IconPlayerPlay } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useState } from "react";
import { api } from "../../api";
import { STEP_VIEWS, type SetupStatus } from "../SetupPage";

type Row = {
  email_id: string;
  sender: string;
  subject: string;
  expected: string | null;
  classification: string;
  correct: boolean | null;
  examples_used: number;
  tool_calls: string;
  tool_errors: string;
  notifications?: string;
};
type Job = { id: string; status: "running" | "done" | "error"; rows?: Row[]; error?: string };

export function ReviewStep({ status }: { status?: SetupStatus }) {
  // the run id lives in the URL (?run=...) so results survive leaving and coming back
  const [params, setParams] = useSearchParams();
  const jobId = params.get("run");
  const setJobId = (id: string) => setParams({ run: id }, { replace: true });
  const job = useQuery({
    queryKey: ["run", jobId],
    queryFn: () => api.get<Job>(`/runs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  });
  const gmail = useQuery({ queryKey: ["gmail-status"], queryFn: () => api.get<{ connected: boolean; preview_count: number }>("/gmail/status") });
  const [count, setCount] = useState<number | string>("");
  const launch = useMutation({
    mutationFn: (source: "samples" | "gmail") =>
      api.post<Job>(source === "samples" ? "/runs/samples" : `/runs/gmail?count=${count || gmail.data?.preview_count || 0}`),
    onSuccess: (j) => setJobId(j.id),
  });
  const running = launch.isPending || job.data?.status === "running";
  const rows = job.data?.rows ?? [];
  const labelled = rows.filter((r) => r.correct !== null);
  const accuracy = labelled.length ? Math.round((100 * labelled.filter((r) => r.correct).length) / labelled.length) : null;

  return (
    <Stack>
      {status && (
        <Group gap="xs">
          {status.order.filter((s) => s !== "review").map((s) => (
            <Badge key={s} color={status.steps[s]?.done ? "green" : "gray"} variant="light">{STEP_VIEWS[s]?.title ?? s}</Badge>
          ))}
        </Group>
      )}
      <Text c="dimmed">
        Run the sample emails, or your latest Gmail emails (read-only: nothing is marked read or sent), through the
        full assistant (stage 04). Replies stay simulated; notifications follow your dry-run setting.
      </Text>
      <Group>
        <Button leftSection={<IconPlayerPlay size={16} />} loading={running && launch.variables !== "gmail"} disabled={running} onClick={() => launch.mutate("samples")}>
          Dry run on sample emails
        </Button>
        <NumberInput w={90} min={1} max={50} value={count} onChange={setCount} placeholder={String(gmail.data?.preview_count ?? "")}
                     aria-label="How many recent emails" />
        <Button variant="light" leftSection={<IconBrandGmail size={16} />} disabled={!gmail.data?.connected || running}
                loading={running && launch.variables === "gmail"} onClick={() => launch.mutate("gmail")}>
          Run on my latest Gmail emails
        </Button>
        {job.data?.status === "running" && <><Loader size="xs" /><Text size="sm">Running… (about a minute with a local model)</Text></>}
        {accuracy !== null && <Badge size="lg" color={accuracy === 100 ? "green" : "yellow"}>Triage accuracy {accuracy}%</Badge>}
      </Group>
      {launch.error && <Alert color="red" title="Could not start the run">{launch.error.message}</Alert>}
      {job.error && <Alert color="red" title="Could not load the run">{job.error.message}</Alert>}
      {job.data?.status === "error" && <Alert color="red">{job.data.error}</Alert>}
      {rows.length > 0 && (
        <Table.ScrollContainer minWidth={720}>
        <Table striped verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr><Table.Th>Email</Table.Th><Table.Th>Triage</Table.Th><Table.Th>Actions</Table.Th><Table.Th>Notifications</Table.Th></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.email_id}>
                <Table.Td>
                  {r.expected ? r.email_id : <><Text size="sm" fw={500} lineClamp={2}>{r.subject}</Text><Text size="xs" c="dimmed">{r.sender}</Text></>}
                </Table.Td>
                <Table.Td>
                  <Badge color={r.correct === null ? "blue" : r.correct ? "green" : "red"} variant="light" style={{ whiteSpace: "nowrap" }}>
                    {r.classification}
                  </Badge>
                  {r.correct === false && <Text size="xs" c="dimmed">expected {r.expected}</Text>}
                </Table.Td>
                <Table.Td><Text size="xs" style={{ whiteSpace: "pre-wrap" }} lineClamp={4}>{r.tool_calls || "—"}</Text>
                  {r.tool_errors && <Text size="xs" c="red">{r.tool_errors}</Text>}</Table.Td>
                <Table.Td><Text size="xs" style={{ whiteSpace: "pre-wrap" }}>{r.notifications || "—"}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}
