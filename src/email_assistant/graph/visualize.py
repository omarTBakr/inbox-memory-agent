"""Render stage graphs locally: Mermaid source + PNG via Graphviz `dot` (no web service)."""

import shutil
import subprocess
from pathlib import Path

from email_assistant.settings import PROJECT_ROOT
from email_assistant.stages import STAGES

GRAPHS_DIR = PROJECT_ROOT / "docs" / "graphs"


def _label(node_id: str) -> str:
    name = node_id.split(":")[-1]
    return {"__start__": "START", "__end__": "END"}.get(name, name)


def to_dot(graph) -> str:
    """Graphviz DOT for a drawable graph (`compiled.get_graph(xray=True)`); subgraphs become clusters."""
    lines = [
        "digraph G {",
        '  rankdir=TB; nodesep=0.5; fontname="Helvetica";',
        '  node [shape=box, style="rounded,filled", fillcolor="#f2f0ff", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
    ]
    clusters: dict[str, list[str]] = {}
    for node_id in graph.nodes:
        prefix = node_id.rsplit(":", 1)[0] if ":" in node_id else ""
        clusters.setdefault(prefix, []).append(node_id)
    for prefix, nodes in clusters.items():
        indent = "  "
        if prefix:
            lines += [f'  subgraph "cluster_{prefix}" {{', f'    label="{prefix}"; style=dashed;']
            indent = "    "
        for node_id in nodes:
            label = _label(node_id)
            shape = ', shape=oval, fillcolor="#bfb6fc"' if label in ("START", "END") else ""
            lines.append(f'{indent}"{node_id}" [label="{label}"{shape}];')
        if prefix:
            lines.append("  }")
    for edge in graph.edges:
        attrs = []
        if edge.conditional:
            attrs.append("style=dashed")
        if edge.data:
            attrs.append(f'label="{edge.data}"')
        lines.append(f'  "{edge.source}" -> "{edge.target}" [{", ".join(attrs)}];')
    lines.append("}")
    return "\n".join(lines)


def render(stage: str) -> list[Path]:
    """Write docs/graphs/<stage>.md (Mermaid) and .png (if Graphviz is installed)."""
    graph = STAGES[stage].build_graph().get_graph(xray=True)
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)
    md = GRAPHS_DIR / f"{stage}.md"
    md.write_text(f"# {stage}\n\n```mermaid\n{graph.draw_mermaid()}```\n")
    written = [md]
    if shutil.which("dot"):
        png = GRAPHS_DIR / f"{stage}.png"
        subprocess.run(["dot", "-Tpng", "-Gdpi=150", "-o", str(png)], input=to_dot(graph), text=True, check=True)
        written.append(png)
    return written
