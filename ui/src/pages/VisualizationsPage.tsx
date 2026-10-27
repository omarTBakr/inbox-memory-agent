// Visualizations: headline numbers from Langfuse, and the Langfuse UI itself (via the local
// embed proxy, which lets only this app frame it).

import { Alert, Anchor, Box, Button, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, Title, useComputedColorScheme } from "@mantine/core";
import { IconExternalLink, IconRefresh } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { StatTile, type Point } from "../components/StatTile";

type Config = { enabled: boolean; embed_url: string; direct_url: string; environment: string; periods: number[]; pages: Record<string, string> };
type Kpi = { value: any; count?: number; series?: Point[]; error?: string };
type Kpis = { kpis: Record<string, Kpi> };

// categorical slots 1-3 of the reference palette (validated all-pairs, light + dark)
const MIX_COLORS = { light: ["#2a78d6", "#eb6834", "#1baf7a"], dark: ["#3987e5", "#d95926", "#199e70"] };
const MIX_ORDER = ["ignore", "notify", "respond"];

const fmt = {
  percent: (v: number) => `${Math.round(v * 100)}%`,
  usd: (v: number) => (v === 0 ? "$0.00" : `$${v < 1 ? v.toFixed(4) : v.toFixed(2)}`),
  seconds: (v: number) => `${(v / 1000).toFixed(1)} s`,
  tokens: (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : String(Math.round(v))),
  count: (v: number) => String(Math.round(v)),
};

function show(k: Kpi | undefined, f: (v: number) => string, empty = "—") {
  if (!k || k.value === null || k.value === undefined) return empty;
  return f(Number(k.value));
}

function TriageMix({ kpi }: { kpi?: Kpi }) {
  const scheme = useComputedColorScheme("light");
  const counts: Record<string, number> = kpi?.value ?? {};
  const total = MIX_ORDER.reduce((sum, l) => sum + (counts[l] ?? 0), 0);
  if (!total) return <Text size="xs" c="dimmed">No decisions yet</Text>;
  return (
    <Stack gap={6}>
      <Box style={{ display: "flex", gap: 2, height: 10 }}>
        {MIX_ORDER.map((l, i) => (counts[l] ?? 0) > 0 && (
          <Box key={l} title={`${l}: ${counts[l]}`}
               style={{ flex: counts[l], background: MIX_COLORS[scheme][i], borderRadius: 4 }} />
        ))}
      </Box>
      <Group gap="sm">
        {MIX_ORDER.map((l, i) => (
          <Group key={l} gap={4}>
            <Box w={8} h={8} style={{ background: MIX_COLORS[scheme][i], borderRadius: 2 }} />
            <Text size="xs">{l} {counts[l] ?? 0}</Text>
          </Group>
        ))}
      </Group>
    </Stack>
  );
}

export function VisualizationsPage() {
  const config = useQuery({ queryKey: ["viz-config"], queryFn: () => api.get<Config>("/visualizations/config") });
  const [days, setDays] = useState("7");
  const [environment, setEnvironment] = useState("current");
  const [page, setPage] = useState("traces");
  const [frameKey, setFrameKey] = useState(0);
  const kpis = useQuery({
    queryKey: ["viz-kpis", days, environment],
    queryFn: () => api.get<Kpis>(`/visualizations/kpis?days=${days}&environment=${environment}`),
  });
  const c = config.data;
  if (c && !c.enabled) return <Alert>Langfuse is disabled (LANGFUSE_ENABLED=false).</Alert>;
  const k = kpis.data?.kpis ?? {};
  const fb = k.feedback;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Visualizations</Title>
        <Group>
          <SegmentedControl size="xs" value={days} onChange={setDays}
                            data={(c?.periods ?? [7]).map((d) => ({ value: String(d), label: `${d} days` }))} />
          <Select size="xs" w={190} value={environment} onChange={(v) => v && setEnvironment(v)} allowDeselect={false}
                  data={[{ value: "current", label: `Environment: ${c?.environment ?? "current"}` }, { value: "all", label: "All environments" }]} />
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="sm">
        <StatTile label="Feedback" value={show(fb, fmt.percent)} format={fmt.percent} series={fb?.series}
                  caption={fb?.count ? `positive · ${fb.count} rating${fb.count === 1 ? "" : "s"}` : "no ratings yet"} onClick={() => setPage("scores")} />
        <StatTile label="Triage mix" value={show(k.triage_mix, () => String(Object.values(k.triage_mix!.value as Record<string, number>).reduce((a, b) => a + b, 0)))}
                  caption="emails handled" onClick={() => setPage("traces")}>
          <TriageMix kpi={k.triage_mix} />
        </StatTile>
        <StatTile label="Cost" value={show(k.cost, fmt.usd)} series={k.cost?.series} format={fmt.usd}
                  caption="model usage, priced in Langfuse" onClick={() => setPage("dashboards")} />
        <StatTile label="Latency p95" value={show(k.latency_p95, fmt.seconds)} series={k.latency_p95?.series} format={fmt.seconds}
                  caption="per traced run" onClick={() => setPage("traces")} />
        <StatTile label="Tokens" value={show(k.tokens, fmt.tokens)} series={k.tokens?.series} format={fmt.tokens}
                  caption="input + output" onClick={() => setPage("dashboards")} />
        <StatTile label="Warnings" value={show(k.warnings, fmt.count)} series={k.warnings?.series} format={fmt.count}
                  caption="failed notification checks" onClick={() => setPage("scores")} />
      </SimpleGrid>
      {Object.entries(k).filter(([, v]) => v.error).map(([name, v]) => (
        <Text key={name} size="xs" c="red">{name}: {v.error}</Text>
      ))}

      {c && (
        <Stack gap="xs">
          <Group justify="space-between">
            <SegmentedControl size="xs" value={page} onChange={setPage}
                              data={Object.keys(c.pages).map((p) => ({ value: p, label: p[0].toUpperCase() + p.slice(1) }))} />
            <Group gap="xs">
              <Text size="xs" c="dimmed">Not logged in? <Anchor href={c.direct_url} target="_blank" size="xs">Log in to Langfuse</Anchor>, then reload.</Text>
              <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} onClick={() => setFrameKey((n) => n + 1)}>Reload</Button>
              <Button size="xs" variant="light" component="a" href={`${c.direct_url}${c.pages[page]}`} target="_blank"
                      rightSection={<IconExternalLink size={14} />}>Open in Langfuse</Button>
            </Group>
          </Group>
          <Box component="iframe" key={frameKey} src={`${c.embed_url}${c.pages[page]}`} title="Langfuse"
               style={{ width: "100%", height: "calc(100vh - 330px)", minHeight: 520, border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }} />
        </Stack>
      )}
    </Stack>
  );
}
