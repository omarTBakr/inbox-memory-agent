# Software Engineering Docs

UML for the Inbox Memory Agent, in PlantUML, based on the code in `src/email_assistant/`.

| Folder | Contents |
|---|---|
| [use_cases/](use_cases/use_cases.md) | User stories UC01–UC19 (story, priority, sprint) |
| [use_case_diagram/](use_case_diagram/use_case_diagram.puml) | Actors, external systems and use cases |
| [class_diagram/](class_diagram/) | One class diagram per subsystem: graph & agents, memory, Gmail, notifications & feedback, config, API & UI |
| [sequence_diagram/](sequence_diagram/) | One sequence diagram per key use case (`ucNN_*.puml`), incl. the Memory page (UC13), rule history (UC17) and settings history + unsaved-changes guard (UC18/19) |
| [system_class_diagram/](system_class_diagram/system_class_diagram.puml) | The whole system on one class diagram |
| [system_sequence_diagram/](system_sequence_diagram/system_sequence_diagram.puml) | End to end: setup → new email → triage/reply → notification → feedback → memory update → review in the Memory page |

## Rendering
Every `.puml` has a rendered `.png` next to it (PlantUML 1.2024.7 + Graphviz). Re-render after editing a diagram:
```bash
# with Docker
docker run --rm -v "$PWD/software_engineering:/data" plantuml/plantuml -tpng "/data/**/*.puml"
# or with Java + plantuml.jar (https://plantuml.com/download)
java -jar plantuml.jar -tpng "software_engineering/**/*.puml"
```
Diagrams also render in the VS Code / JetBrains PlantUML plugins.
