import { Alert, Button, Group, Loader, Stack, Text } from "@mantine/core";
import { IconDatabase, IconRefresh } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Check } from "../../api";
import { CheckList } from "../../components/CheckList";

export function HealthStep() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.get<{ ok: boolean; services: Record<string, Check> }>("/health") });
  const dbInit = useMutation({
    mutationFn: () => api.post("/health/db-init"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["health"] });
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
    },
  });

  return (
    <Stack>
      <Text c="dimmed">The services the assistant needs. Start them with <code>make up</code>.</Text>
      {health.isLoading ? <Loader /> : health.data && <CheckList checks={health.data.services} />}
      {health.error && <Alert color="red">{String(health.error)}</Alert>}
      {dbInit.error && <Alert color="red">{String(dbInit.error)}</Alert>}
      <Group>
        <Button variant="light" leftSection={<IconRefresh size={16} />} loading={health.isFetching} onClick={() => health.refetch()}>
          Check again
        </Button>
        <Button variant="light" leftSection={<IconDatabase size={16} />} loading={dbInit.isPending} onClick={() => dbInit.mutate()}>
          Initialise database
        </Button>
      </Group>
    </Stack>
  );
}
