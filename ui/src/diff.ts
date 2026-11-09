// Small diff helpers for the history views: which config fields changed, and a word diff of texts.

import { stableJson } from "./unsaved";

export type FieldChange = { path: string; before: unknown; after: unknown };

/** Leaf paths ("user.name", "contacts.items") whose value differs; arrays compare as a whole. */
export function changedFields(before: unknown, after: unknown, path = ""): FieldChange[] {
  const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
  if (isObj(before) && isObj(after)) {
    const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
    return keys.flatMap((k) => changedFields(before[k], after[k], path ? `${path}.${k}` : k));
  }
  return stableJson(before) === stableJson(after) ? [] : [{ path, before, after }];
}

export type DiffPart = { text: string; kind: "same" | "added" | "removed" };

/** Word-level diff (longest common subsequence); fine for prompts of a few hundred words. */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/), b = after.split(/(\s+)/);
  const n = a.length, m = b.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const parts: DiffPart[] = [];
  const push = (text: string, kind: DiffPart["kind"]) => {
    const last = parts[parts.length - 1];
    if (last?.kind === kind) last.text += text;
    else parts.push({ text, kind });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { push(a[i], "same"); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) push(a[i++], "removed");
    else push(b[j++], "added");
  }
  while (i < n) push(a[i++], "removed");
  while (j < m) push(b[j++], "added");
  return parts;
}
