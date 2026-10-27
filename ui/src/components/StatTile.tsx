// KPI stat tile: value + caption + optional sparkline (single series, 2px line, hover tooltip).
// Text uses text tokens; only the line carries color.

import { Box, Paper, Stack, Text, UnstyledButton, useComputedColorScheme } from "@mantine/core";
import { useState, type ReactNode } from "react";

export type Point = { day: string; value: number | null };

// categorical slot 1 of the reference palette, stepped per mode
const LINE = { light: "#2a78d6", dark: "#3987e5" };

function Sparkline({ series, format }: { series: Point[]; format: (v: number) => string }) {
  const scheme = useComputedColorScheme("light");
  const [hover, setHover] = useState<number | null>(null);
  const points = series.map((p) => p.value);
  const known = points.filter((v): v is number => v !== null);
  if (known.length < 2) return <Box h={32} />;
  const w = 160, h = 32, pad = 3;
  const min = Math.min(...known), max = Math.max(...known);
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const y = (v: number) => (max === min ? h / 2 : h - pad - ((v - min) * (h - 2 * pad)) / (max - min));
  const path = points.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" L ");
  const active = hover !== null && points[hover] !== null ? hover : null;
  return (
    <Box pos="relative">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="Daily trend"
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const rect = e.currentTarget.getBoundingClientRect();
             setHover(Math.round(((e.clientX - rect.left) / rect.width) * (points.length - 1)));
           }}>
        <path d={`M ${path}`} fill="none" stroke={LINE[scheme]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {active !== null && (
          <circle cx={x(active)} cy={y(points[active]!)} r={4} fill={LINE[scheme]}
                  stroke="var(--mantine-color-body)" strokeWidth={2} />
        )}
      </svg>
      {active !== null && (
        <Text size="xs" c="dimmed" pos="absolute" top={-18} right={0}>
          {series[active].day}: {format(points[active]!)}
        </Text>
      )}
    </Box>
  );
}

type Props = {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  series?: Point[];
  format?: (v: number) => string;
  onClick?: () => void;
  children?: ReactNode;
};

export function StatTile({ label, value, caption, series, format = String, onClick, children }: Props) {
  return (
    <UnstyledButton onClick={onClick} style={{ display: "block", height: "100%" }}>
      <Paper withBorder p="sm" radius="md" h="100%">
        <Stack gap={4}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
          <Text fz={26} fw={700} lh={1.1}>{value}</Text>
          {caption && <Text size="xs" c="dimmed">{caption}</Text>}
          {series && <Sparkline series={series} format={format} />}
          {children}
        </Stack>
      </Paper>
    </UnstyledButton>
  );
}
