# Use Cases (User Stories)

Roles: **Mailbox owner** (the person whose inbox is handled), **Admin** (sets the app up: Gmail, models, Telegram),
**Developer** (works on stages, prompts and evaluation).
Priority: High / Medium / Low. Sprints follow the project's stages: Sprint 1 = baseline, 2 = semantic memory,
3 = episodic memory + Gmail, 4 = procedural memory + notifications/feedback, 5 = UI review: Memory page, version history,
unsaved-changes guard.

| ID | User story | Priority | Sprint |
|---|---|---|---|
| UC01 | As a **mailbox owner** user, I want to be able to **have new Gmail messages picked up and handled automatically as they arrive** in order to **stop triaging my inbox by hand**. | High | Sprint 3 |
| UC02 | As a **mailbox owner** user, I want to be able to **have every email classified as ignore, notify or respond** in order to **focus only on the emails that matter**. | High | Sprint 1 |
| UC03 | As a **mailbox owner** user, I want to be able to **let the assistant draft, review and send replies using tools (calendar availability, scheduling, write email)** in order to **save the time spent on routine answers**. | High | Sprint 1 |
| UC04 | As a **mailbox owner** user, I want to be able to **have the assistant remember facts about my contacts, projects and preferences** in order to **get replies that use the right context**. | High | Sprint 2 |
| UC05 | As a **mailbox owner** user, I want to be able to **rate each handled email with 👍 / 👎 on Telegram** in order to **teach the assistant which decisions were right**. | High | Sprint 4 |
| UC06 | As a **mailbox owner** user, I want to be able to **correct an email's label (ignore / notify / respond)** in order to **have similar emails handled correctly next time (episodic few-shot examples)**. | High | Sprint 3 |
| UC07 | As a **mailbox owner** user, I want to be able to **explain in free text what was wrong (Telegram reply or `make teach`)** in order to **have the triage rules and agent instructions rewritten (procedural memory)**. | Medium | Sprint 4 |
| UC08 | As a **mailbox owner** user, I want to be able to **press "Not spam" on an email found in Spam** in order to **move it to my Inbox and have the assistant surface similar emails in the future**. | Medium | Sprint 4 |
| UC09 | As a **mailbox owner** user, I want to be able to **receive a Telegram notification for the outcomes I choose (notify_on)** in order to **stay informed about what the assistant did on my behalf**. | High | Sprint 4 |
| UC10 | As an **admin** user, I want to be able to **connect my Gmail account through Google OAuth (upload client JSON, connect, test)** in order to **let the assistant read and act on my mailbox**. | High | Sprint 3 |
| UC11 | As an **admin** user, I want to be able to **choose the chat model and embeddings provider (Ollama or API) and probe their compatibility** in order to **run the assistant on the model that suits my hardware and budget**. | High | Sprint 2 |
| UC12 | As a **mailbox owner** user, I want to be able to **get a daily digest of the emails the assistant ignored** in order to **catch important emails that were wrongly ignored**. | Medium | Sprint 4 |
| UC13 | As a **mailbox owner** user, I want to be able to **browse, search by meaning and forget stored facts and labelled examples on the Memory page** in order to **stay in control of what the assistant keeps about me and remove wrong or duplicate memories**. | Medium | Sprint 5 |
| UC14 | As an **admin** user, I want to be able to **go through a setup wizard whose settings are saved versioned and whose secrets are stored encrypted** in order to **configure the app safely without editing files**. | High | Sprint 3 |
| UC15 | As a **developer** user, I want to be able to **run each stage as an MLflow run and inspect Langfuse traces and KPI dashboards** in order to **measure triage accuracy, cost and the effect of each memory type**. | Medium | Sprint 2 |
| UC16 | As an **admin** user, I want to be able to **start, stop and trigger the Gmail watcher and see its status in the UI** in order to **know whether new mail is being processed**. | Medium | Sprint 3 |
| UC17 | As a **mailbox owner** user, I want to be able to **see every learned version of a rule with a word diff and the feedback that caused it, and reset it to my profile's text** in order to **understand and undo what my feedback changed**. | Medium | Sprint 5 |
| UC18 | As an **admin** user, I want to be able to **see the saved versions of a settings section with the fields each changed, and load an old version back into the form** in order to **find and roll back a bad configuration change**. | Low | Sprint 5 |
| UC19 | As an **admin** user, I want to be able to **be warned before leaving a form with unsaved changes** in order to **not lose edits by switching steps, tabs or pages**. | High | Sprint 5 |
