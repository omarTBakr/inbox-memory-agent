// One config section: schema-driven form + its secrets + save. Extra actions (tests,
// probes) are passed as children and get the current, unsaved values.

import { ActionIcon, Alert, Badge, Button, Group, Loader, PasswordInput, Stack, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconDeviceFloppy, IconHistory, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type FieldError, type Option, type SectionConfig, type SectionSchema } from "../api";
import { setDirty, stableJson } from "../unsaved";
import { ConfigHistory } from "./ConfigHistory";
import { humanize, SchemaForm } from "./SchemaForm";

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
  const [historyOpen, setHistoryOpen] = useState(false);

  // what the server last sent; edits are compared against it
  const baseline = useRef<Record<string, any> | null>(null);
  const resetNext = useRef(false);

  useEffect(() => {
    if (!config.data) return;
    const server = config.data.data;
    const old = baseline.current;
    if (old === null || resetNext.current || stableJson(value) === stableJson(old)) {
      setValue(server); // no unsaved edits: take the server's values
      setErrors(config.data.valid ? [] : config.data.errors);
    } else {
      // unsaved edits (e.g. the watcher switch saved auto_trigger meanwhile):
      // take server changes only for fields the user hasn't touched
      setValue((current) => {
        const merged = { ...server };
        for (const k of Object.keys(current)) {
          if (stableJson(current[k]) !== stableJson(old[k])) merged[k] = current[k];
        }
        return merged;
      });
    }
    baseline.current = server;
    resetNext.current = false;
  }, [config.data]);

  const isDirty = !!config.data && (stableJson(value) !== stableJson(config.data.data)
    || Object.values(secretValues).some(Boolean));
  useEffect(() => setDirty(section, isDirty), [section, isDirty]);
  useEffect(() => () => setDirty(section, false), [section]);

  const mutation = useMutation({
    mutationFn: () => api.put<{ version: number }>(`/config/${section}`, { data: value, secrets: secretValues }),
    onSuccess: (res) => {
      resetNext.current = true;
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

  const clearSecret = useMutation({
    mutationFn: (name: string) => api.del(`/config/${section}/secrets/${name}`),
    onSuccess: (_, name) => {
      queryClient.invalidateQueries({ queryKey: ["config", section] });
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      notifications.show({ message: `${humanize(name)} removed` });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
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
          <>
            <Badge color="green" variant="light">Saved · v{config.data.meta?.version}</Badge>
            <Button size="compact-xs" variant="subtle" leftSection={<IconHistory size={14} />} onClick={() => setHistoryOpen(true)}>
              History
            </Button>
          </>
        ) : (
          <Badge color="yellow" variant="light">Not saved yet · showing defaults</Badge>
        )}
        {isDirty && <Badge color="orange" variant="light">Unsaved changes</Badge>}
        <Text size="xs" c="dimmed">Fields marked * are required.</Text>
      </Group>
      {schema.data.schema.description && <Text c="dimmed">{schema.data.schema.description}</Text>}

      <SchemaForm schema={schema.data.schema} value={value} onChange={setValue} errors={errors} optionsOverride={optionsOverride} />

      {/* errors no field shows (e.g. on secrets or the whole section) */}
      {unmatched(errors, schema.data.schema).map((e, i) => (
        <Alert key={i} color="red">{e.loc.length ? `${e.loc.join(".")}: ` : ""}{e.msg}</Alert>
      ))}

      {secrets.map((s) => (
        <PasswordInput
          key={s.name}
          label={humanize(s.name)}
          description={s.description}
          placeholder={config.data!.secrets[s.name] ? "Saved — leave empty to keep it" : "Not set"}
          value={secretValues[s.name] ?? ""}
          onChange={(e) => setSecretValues({ ...secretValues, [s.name]: e.currentTarget.value })}
          rightSectionWidth={84}
          rightSection={config.data!.secrets[s.name] ? (
            <Group gap={4} wrap="nowrap">
              <Badge size="xs" color="green">set</Badge>
              <Tooltip label="Remove the saved value">
                <ActionIcon size="sm" variant="subtle" color="red" aria-label={`Remove saved ${humanize(s.name)}`}
                            loading={clearSecret.isPending && clearSecret.variables === s.name}
                            onClick={() => window.confirm(`Remove the saved ${humanize(s.name)}?`) && clearSecret.mutate(s.name)}>
                  <IconTrash size={14} />
                </ActionIcon>
              </Tooltip>
            </Group>
          ) : null}
        />
      ))}

      {children?.(ctx)}

      <ConfigHistory section={section} opened={historyOpen} onClose={() => setHistoryOpen(false)}
                     current={config.data.meta?.version} onLoad={(data) => { setValue(data); setErrors([]); }} />

      <Group>
        <Button leftSection={<IconDeviceFloppy size={16} />} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Save
        </Button>
      </Group>
    </Stack>
  );
}

// a 422 error whose first path part isn't a form field would otherwise be dropped
function unmatched(errors: FieldError[], schema: SectionSchema["schema"]): FieldError[] {
  const fields = new Set(Object.keys((schema as { properties?: Record<string, unknown> }).properties ?? {}));
  // section-wide errors (empty loc) are already shown by SchemaForm
  return errors.filter((e) => e.loc.length > 0 && !fields.has(String(e.loc[0])));
}
