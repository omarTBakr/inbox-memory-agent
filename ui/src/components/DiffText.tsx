// A word diff: removed words struck through in red, added words in green. Colors come with
// text styling too (strike / underline) so the change reads without color.

import { Text } from "@mantine/core";
import { wordDiff } from "../diff";

export function DiffText({ before, after }: { before: string; after: string }) {
  return (
    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
      {wordDiff(before, after).map((p, i) =>
        p.kind === "same" ? <span key={i}>{p.text}</span>
        : p.kind === "added" ? (
          <ins key={i} style={{ background: "var(--mantine-color-green-light)", color: "var(--mantine-color-green-light-color)" }}>{p.text}</ins>
        ) : (
          <del key={i} style={{ background: "var(--mantine-color-red-light)", color: "var(--mantine-color-red-light-color)" }}>{p.text}</del>
        ),
      )}
    </Text>
  );
}
