import { Alert, Button, Divider, Group, Stack, Text } from "@mantine/core";
import { IconStethoscope } from "@tabler/icons-react";
import { useState } from "react";
import { api, type Check, type Option } from "../../api";
import { CheckList } from "../../components/CheckList";
import { SectionEditor, type SectionContext } from "../../components/SectionEditor";
import { ModelList, useProviders } from "./ModelStep";

function Probe({ ctx }: { ctx: SectionContext }) {
  const [result, setResult] = useState<(Check & { dims?: number }) | null>(null);
  const [loading, setLoading] = useState(false);
  const run = async () => {
    setLoading(true);
    try {
      setResult(await api.post("/models/probe-embeddings", { data: ctx.value, api_key: ctx.secretValues.api_key ?? "" }));
    } catch (e) {
      setResult({ ok: false, detail: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };
  return (
    <Stack gap="xs">
      <Divider label="Test" labelPosition="left" />
      <Alert color="yellow">
        Memories are stored with these vectors. Changing the model or dimensions later means existing memories must be re-indexed.
      </Alert>
      <Group>
        <Button variant="light" leftSection={<IconStethoscope size={16} />} loading={loading} onClick={run}>Test embeddings</Button>
        {result?.dims && result.dims !== ctx.value.dims && (
          <Button variant="subtle" onClick={() => ctx.setValue({ ...ctx.value, dims: result.dims })}>
            Use {result.dims} dimensions
          </Button>
        )}
      </Group>
      {result && <CheckList checks={{ embeddings: result }} />}
      <Text size="xs" c="dimmed">Dimensions must match what the model returns.</Text>
    </Stack>
  );
}

export function EmbeddingsStep() {
  const providers = useProviders("embedding_providers");
  const [models, setModels] = useState<Option[]>([]);
  return (
    <SectionEditor section="embeddings" optionsOverride={{ embedding_models: models }}
                   showSecret={(_, v) => !!providers.find((p) => p.value === v.provider)?.api_key}>
      {(ctx) => (
        <Stack>
          <ModelList ctx={ctx} embeddings onModels={setModels} />
          <Probe ctx={ctx} />
        </Stack>
      )}
    </SectionEditor>
  );
}
