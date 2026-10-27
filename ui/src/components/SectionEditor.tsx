// One config section: schema-driven form + its secrets + save. Extra actions (tests,
// probes) are passed as children and get the current, unsaved values.

import { Alert, Badge, Button, Group, Loader, PasswordInput, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconDeviceFloppy } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type FieldError, type Option, type SectionConfig, type SectionSchema } from "../api";
import { SchemaForm } from "./SchemaForm";

export type SectionContext = {
  value: Record<string, any>;
  setValue: (v: Record<string, any>) => void;
  secretValues: Record<string, string>;
  config: SectionConfig;
  save: () => Promise<void>;
};

type Props = {
  section: string;
  optionsOverride?: Record<string, Option[]>;
  // hide some secrets depending on the current values (e.g. no API key for Ollama)
  showSecret?: (name: string, value: Record<string, any>) => boolean;
  children?: (ctx: SectionContext) => ReactNode;
  onSaved?: () => void;
};

export function SectionEditor({ section, optionsOverride, showSecret, children, onSaved }: Props) {
  const queryClient = useQueryClient();
  const schema = useQuery({ queryKey: ["schema", section], queryFn: () => api.get<SectionSchema>(`/schema/${section}`) });
  const config = useQuery({ queryKey: ["config", section], queryFn: () => api.get<SectionConfig>(`/config/${section}`) });
  const [value, setValue] = useState<Record<string, any>>({});
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<FieldError[]>([]);

  useEffect(() => {
    if (config.data) {
      setValue(config.data.data);
      setErrors(config.data.valid ? [] : config.data.errors);
    }
  }, [config.data]);

  const mutation = useMutation({
    mutationFn: () => api.put<{ version: number }>(`/config/${section}`, { data: value, secrets: secretValues }),
    onSuccess: (res) => {
      setErrors([]);
      setSecretValues({});
      queryClient.invalidateQueries({ queryKey: ["config", section] });
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      notifications.show({ color: "green", icon: <IconCheck size={16} />, message: `Saved (version ${res.version})` });
      onSaved?.();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fieldErrors.length) setErrors(e.fieldErrors);
      notifications.show({ color: "red", message: e instanceof ApiError && !e.fieldErrors.length ? e.message : "Please fix the highlighted fields" });
    },
  });

  if (schema.isLoading || config.isLoading) return <Loader />;
  if (schema.error || config.error || !schema.data || !config.data) {
    return <Alert color="red">Could not load {section}: {String(schema.error ?? config.error)}</Alert>;
  }

  const secrets = schema.data.secrets.filter((s) => !showSecret || showSecret(s.name, value));
  const ctx: SectionContext = { value, setValue, secretValues, config: config.data, save: () => mutation.mutateAsync().then(() => undefined) };

  return (
    <Stack gap="lg">
      <Group gap="xs">
        {config.data.source === "saved" ? (
          <Badge color="green" variant="light">Saved · v{config.data.meta?.version}</Badge>
        ) : (
          <Badge color="yellow" variant="light">Not saved yet · showing defaults</Badge>
        )}
        <Text size="xs" c="dimmed">Fields marked * are required.</Text>
      </Group>
      {schema.data.schema.description && <Text c="dimmed">{schema.data.schema.description}</Text>}

      <SchemaForm schema={schema.data.schema} value={value} onChange={setValue} errors={errors} optionsOverride={optionsOverride} />

      {secrets.map((s) => (
        <PasswordInput
          key={s.name}
          label={s.name.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}
          description={s.description}
          placeholder={config.data!.secrets[s.name] ? "Saved — leave empty to keep it" : "Not set"}
          value={secretValues[s.name] ?? ""}
          onChange={(e) => setSecretValues({ ...secretValues, [s.name]: e.currentTarget.value })}
          rightSectionWidth={70}
          rightSection={config.data!.secrets[s.name] ? <Badge size="xs" color="green">set</Badge> : null}
        />
      ))}

      {children?.(ctx)}

      <Group>
        <Button leftSection={<IconDeviceFloppy size={16} />} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Save
        </Button>
      </Group>
    </Stack>
  );
}
