// Renders a form from the backend's JSON schema (pydantic). Nothing about the fields is
// hard-coded here: required/optional, labels, help, choices and widgets come from the schema
// and its "ui" hints (options, custom, multiline, required_if, secret).

import {
  ActionIcon,
  Autocomplete,
  Badge,
  Button,
  Fieldset,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  Switch,
  TagsInput,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, type FieldError, type Option } from "../api";

type Path = (string | number)[];

type Props = {
  schema: any;
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  errors?: FieldError[];
  // option lists supplied by the page instead of /api/options (e.g. models of the chosen provider)
  optionsOverride?: Record<string, Option[]>;
};

const humanize = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function resolve(root: any, node: any): any {
  if (node?.$ref) return resolve(root, root.$defs[node.$ref.split("/").pop()]);
  if (node?.anyOf) {
    const inner = node.anyOf.find((n: any) => n.type !== "null");
    return { ...resolve(root, inner), ...omit(node, ["anyOf"]), nullable: true };
  }
  return node;
}

const omit = (o: any, keys: string[]) => Object.fromEntries(Object.entries(o).filter(([k]) => !keys.includes(k)));

function setIn(obj: any, path: Path, value: any): any {
  if (!path.length) return value;
  const [head, ...rest] = path;
  const copy = Array.isArray(obj) ? [...obj] : { ...(obj ?? {}) };
  copy[head as any] = setIn(copy[head as any], rest, value);
  return copy;
}

function useOptions(name: string | undefined, override?: Record<string, Option[]>) {
  const query = useQuery({
    queryKey: ["options", name],
    queryFn: () => api.get<Option[]>(`/options/${name}`),
    enabled: !!name && !override?.[name],
    staleTime: Infinity,
  });
  if (!name) return [];
  return override?.[name] ?? query.data ?? [];
}

export function SchemaForm({ schema, value, onChange, errors = [], optionsOverride }: Props) {
  const errorAt = (path: Path) =>
    errors
      .filter((e) => e.loc.join(".") === path.join(".") || (path.length === 0 && e.loc.length === 0))
      .map((e) => e.msg)
      .join("; ") || undefined;
  const formErrors = errors.filter((e) => e.loc.length === 0).map((e) => e.msg);

  return (
    <Stack gap="md">
      {formErrors.length > 0 && <Text c="red" size="sm">{formErrors.join("; ")}</Text>}
      <ObjectFields
        root={schema}
        node={schema}
        path={[]}
        value={value}
        onChange={(path, v) => onChange(setIn(value, path, v))}
        errorAt={errorAt}
        optionsOverride={optionsOverride}
      />
    </Stack>
  );
}

type FieldProps = {
  root: any;
  node: any;
  path: Path;
  value: any;
  onChange: (path: Path, value: any) => void;
  errorAt: (path: Path) => string | undefined;
  optionsOverride?: Record<string, Option[]>;
};

function ObjectFields({ root, node, path, value, onChange, errorAt, optionsOverride }: FieldProps) {
  const required: string[] = node.required ?? [];
  return (
    <>
      {Object.entries<any>(node.properties ?? {}).map(([key, prop]) => {
        const hint = prop.ui ?? {};
        const conditional =
          hint.required_if && (value?.[hint.required_if.field] ?? []).includes(hint.required_if.contains);
        return (
          <Field
            key={key}
            name={key}
            required={required.includes(key) || !!hint.required || conditional}
            root={root}
            node={prop}
            path={[...path, key]}
            value={value?.[key]}
            onChange={onChange}
            errorAt={errorAt}
            optionsOverride={optionsOverride}
          />
        );
      })}
    </>
  );
}

function FieldLabel({ name, required }: { name: string; required: boolean }) {
  return (
    <>
      {humanize(name)}
      {!required && <Badge size="xs" variant="light" color="gray" ml={6} style={{ verticalAlign: "middle" }}>optional</Badge>}
    </>
  );
}

function Field(props: FieldProps & { name: string; required: boolean }) {
  const { root, path, value, onChange, errorAt, optionsOverride, name, required } = props;
  const node = resolve(root, props.node);
  const hint = props.node.ui ?? node.ui ?? {};
  const options = useOptions(hint.options, optionsOverride);
  const label: ReactNode = <FieldLabel name={name} required={required} />;
  const common = {
    label,
    description: props.node.description ?? node.description,
    withAsterisk: required,
    error: errorAt(path) ?? (typeof value === "string" && value.includes("TODO") ? "Still a placeholder: please fill in" : undefined),
  };
  const set = (v: any) => onChange(path, v);
  const data = options.map((o) => ({ value: String(o.value), label: o.label }));

  if (node.type === "object" && node.properties) {
    return (
      <Fieldset legend={<FieldLabel name={name} required={required} />}>
        {common.description && <Text size="sm" c="dimmed" mb="xs">{common.description}</Text>}
        <Stack gap="sm">
          <ObjectFields {...props} node={node} />
        </Stack>
      </Fieldset>
    );
  }

  if (node.type === "array") {
    const items = resolve(root, node.items);
    if (items.type === "object") return <ObjectList {...props} items={items} label={label} />;
    if (items.enum) {
      return <MultiSelect {...common} data={items.enum} value={value ?? []} onChange={set} />;
    }
    if (hint.options && !hint.custom) {
      return <MultiSelect {...common} data={data} value={value ?? []} onChange={set} searchable />;
    }
    return <TagsInput {...common} data={data} value={value ?? []} onChange={set} placeholder="Type and press Enter" />;
  }

  if (node.enum) {
    return (
      <Select {...common} data={node.enum.map(String)} value={value ?? null}
              onChange={(v) => set(v)} clearable={node.nullable} placeholder={node.nullable ? "Provider default" : undefined} />
    );
  }

  if (node.type === "boolean") {
    return <Switch label={label} description={common.description} checked={!!value} onChange={(e) => set(e.currentTarget.checked)} />;
  }

  if (node.type === "integer" || node.type === "number") {
    if (hint.options) {
      return (
        <Autocomplete {...common} data={data} value={value === undefined || value === null ? "" : String(value)}
                      onChange={(v) => set(v === "" ? null : Number(v))} />
      );
    }
    return (
      <NumberInput {...common} value={value ?? ""} min={node.minimum} max={node.maximum}
                   decimalScale={node.type === "integer" ? 0 : 2} onChange={(v) => set(v === "" ? null : v)} />
    );
  }

  if (hint.options) {
    return hint.custom ? (
      <Autocomplete {...common} data={data} value={value ?? ""} onChange={set} />
    ) : (
      <Select {...common} data={data} value={value ?? null} onChange={set} searchable />
    );
  }
  if (hint.multiline) return <Textarea {...common} value={value ?? ""} onChange={(e) => set(e.currentTarget.value)} autosize minRows={2} />;
  return <TextInput {...common} value={value ?? ""} onChange={(e) => set(e.currentTarget.value)} />;
}

function ObjectList(props: FieldProps & { name: string; required: boolean; items: any; label: ReactNode }) {
  const { value, path, onChange, items, label } = props;
  const list: any[] = value ?? [];
  return (
    <Fieldset legend={label}>
      {props.node.description && <Text size="sm" c="dimmed" mb="xs">{props.node.description}</Text>}
      <Stack gap="xs">
        {list.map((item, i) => (
          <Group key={i} align="flex-end" wrap="nowrap">
            <Group grow style={{ flex: 1 }}>
              <ObjectFields {...props} node={items} path={[...path, i]} value={item} />
            </Group>
            <ActionIcon variant="subtle" color="red" aria-label="Remove"
                        onClick={() => onChange(path, list.filter((_, j) => j !== i))}>
              <IconTrash size={16} />
            </ActionIcon>
          </Group>
        ))}
        <Button variant="light" size="xs" leftSection={<IconPlus size={14} />} w="fit-content"
                onClick={() => onChange(path, [...list, {}])}>
          Add
        </Button>
      </Stack>
    </Fieldset>
  );
}
