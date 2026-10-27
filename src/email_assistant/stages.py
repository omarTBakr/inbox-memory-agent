"""Registry of stages: the one place that maps a stage id to its graph builder."""

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    id: str
    module: str
    uses_store: bool

    def build_graph(self, profile=None, store=None):
        return importlib.import_module(self.module).build_graph(profile, store)


STAGES = {
    s.id: s
    for s in [
        Stage("01_baseline", "email_assistant.graph.baseline", uses_store=False),
        Stage("02_semantic_memory", "email_assistant.graph.semantic", uses_store=True),
        Stage("03_semantic_episodic", "email_assistant.graph.episodic", uses_store=True),
        Stage("04_semantic_episodic_procedural", "email_assistant.graph.procedural", uses_store=True),
    ]
}
