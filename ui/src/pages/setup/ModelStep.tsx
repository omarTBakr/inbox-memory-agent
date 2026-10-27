import { Alert, Button, Divider, Group, Stack, Text } from "@mantine/core";
import { IconListSearch, IconStethoscope } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Check, type Option } from "../../api";
import { CheckList } from "../../components/CheckList";
import { SectionEditor, type SectionContext } from "../../components/SectionEditor";

type Provider = Option & { kind: "local" | "api"; api_key: boolean; base_url: string };
type ModelOption = Option & { capabilities: string[] };

// shared by the chat model and embeddings steps
export function useProviders(name: "providers" | "embedding_providers") {
  return useQuery({ queryKey: ["options", name], queryFn: () => api.get<Provider[]>(`/options/${name}`), staleTime: Infinity }).data ?? [];
}

export function ModelList({ ctx, embeddings, onModels }: { ctx: SectionContext; embeddings: boolean; onModels: (m: Option[]) => void }) {
  const { value, secretValues } = ctx;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const models = await api.post<ModelOption[]>("/options/models", {
        provider: value.provider, base_url: value.base_url ?? "", api_key: secretValues.api_key ?? "", embeddings,
      });
      onModels(models.map((m) => ({ ...m, label: m.capabilities.length ? `${m.value}  ·  ${m.capabilities.join(", ")}` : String(m.value) })));
    } catch (e) {
      setError((e as Error).message);
      onModels([]);
    } finally {
      setLoading(false);
    }
  };
  // local models need no key, so list them as soon as the provider is picked
  useEffect(() => {
    if (value.provider === "ollama") load();
  }, [value.provider, value.base_url]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Stack gap="xs">
      <Group>
        <Button variant="light" leftSection={<IconListSearch size={16} />} loading={loading} onClick={load}>
          Load available models
        </Button>
        <Text size="sm" c="dimmed">API providers need the key typed below or already saved.</Text>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
    </Stack>
  );
}

function Probe({ ctx }: { ctx: SectionContext }) {
  const [result, setResult] = useState<{ ok: boolean; checks: Record<string, Check> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.post("/models/probe", { data: ctx.value, api_key: ctx.secretValues.api_key ?? "" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <Stack gap="xs">
      <Divider label="Compatibility test" labelPosition="left" />
      <Text size="sm" c="dimmed">Checks the two things the assistant needs: structured answers (triage) and tool calls (replies, calendar).</Text>
      <Group>
        <Button variant="light" leftSection={<IconStethoscope size={16} />} loading={loading} onClick={run}>Test this model</Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      {result && (
        <>
          <Alert color={result.ok ? "green" : "red"}>{result.ok ? "This model works for the assistant." : "This model failed a check; try another model or turn reasoning on/off."}</Alert>
          <CheckList checks={result.checks} />
        </>
      )}
    </Stack>
  );
}

export function ModelStep() {
  const providers = useProviders("providers");
  const [models, setModels] = useState<Option[]>([]);
  const needsKey = (v: Record<string, any>) => !!providers.find((p) => p.value === v.provider)?.api_key;
  return (
    <SectionEditor section="model" optionsOverride={{ models }} showSecret={(_, v) => needsKey(v)}>
      {(ctx) => (
        <Stack>
          <ModelList ctx={ctx} embeddings={false} onModels={setModels} />
          <Probe ctx={ctx} />
        </Stack>
      )}
    </SectionEditor>
  );
}
