// "What should I do?": foldable step-by-step help for one setup step, from config/guides.yml.

import { Accordion, Anchor, Code, List, Text, ThemeIcon } from "@mantine/core";
import { IconHelp } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "../api";

type Section = { title: string; steps: string[]; notes?: string[] };
type StepGuide = { title: string; sections: Section[] };

// `code`, **bold** and [text](url) — the only formatting the guides use
function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g).map((part, i) => {
    if (part.startsWith("`")) return <Code key={i}>{part.slice(1, -1)}</Code>;
    if (part.startsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) return <Anchor key={i} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</Anchor>;
    return part;
  });
}

export function Guide({ step }: { step: string }) {
  const guide = useQuery({ queryKey: ["guide", step], queryFn: () => api.get<StepGuide>(`/guides/${step}`), staleTime: Infinity });
  if (!guide.data) return null;
  return (
    <Accordion variant="contained" mb="lg">
      <Accordion.Item value="help">
        <Accordion.Control icon={<ThemeIcon variant="light" size="sm"><IconHelp size={14} /></ThemeIcon>}>
          What should I do?
        </Accordion.Control>
        <Accordion.Panel>
          <Accordion variant="separated" multiple>
            {guide.data.sections.map((section) => (
              <Accordion.Item key={section.title} value={section.title}>
                <Accordion.Control><Text fw={500}>{section.title}</Text></Accordion.Control>
                <Accordion.Panel>
                  <List type="ordered" spacing={6} size="sm">
                    {section.steps.map((s, i) => <List.Item key={i}>{inline(s)}</List.Item>)}
                  </List>
                  {section.notes && (
                    <List spacing={4} size="xs" c="dimmed" mt="sm">
                      {section.notes.map((n, i) => <List.Item key={i}>{inline(n)}</List.Item>)}
                    </List>
                  )}
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
