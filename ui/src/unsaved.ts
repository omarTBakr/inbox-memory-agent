// Which config sections have unsaved edits, so leaving the page (nav, Back/Next, tabs,
// closing the tab) can warn first. SectionEditor reports; navigation asks `confirmLeave()`.

const dirty = new Set<string>();

export function setDirty(section: string, isDirty: boolean): void {
  if (isDirty) dirty.add(section);
  else dirty.delete(section);
}

/** true when it's fine to leave: nothing unsaved, or the user agreed to discard it. */
export function confirmLeave(): boolean {
  if (dirty.size === 0) return true;
  const ok = window.confirm(`You have unsaved changes (${[...dirty].join(", ")}). Leave without saving?`);
  if (ok) dirty.clear();
  return ok;
}

window.addEventListener("beforeunload", (e) => {
  if (dirty.size > 0) e.preventDefault();
});

/** JSON with sorted keys, so key order never makes a form look edited. */
export function stableJson(value: unknown): string {
  return JSON.stringify(value, (_, v) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
}
