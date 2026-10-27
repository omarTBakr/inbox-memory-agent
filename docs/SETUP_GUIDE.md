# Setup guide

<!-- Generated from config/guides.yml by `make docs`; edit that file instead. -->

The setup wizard (http://localhost:5173/setup) walks through these steps in order. Each step saves on its own, so you can come back later; Settings shows the same forms afterwards.

## 1. System

### Start the services

1. Start the containers with `make up` (Postgres, Langfuse, MLflow).
2. Make sure Ollama is running on this machine if you use local models (`ollama serve`, usually already running).
3. Press **Check again**; every row should be green.
4. First time only, press **Initialise database** to create the tables.

> A red row shows the error; `make logs S=<service>` shows that container's logs.  

## 2. Profile

### Tell the assistant who you are

1. Fill in every field marked with a red `*`; fields still showing `TODO` are flagged.
2. Pick your time zone and working days; meeting length and buffer drive the calendar suggestions.
3. Write triage rules in plain language (what to ignore, what to tell you about, what to answer).
4. List the topics the assistant must never decide for you under **Escalate when** (approvals, money, legal...); it sends a holding reply and flags those emails.
5. Press **Save**.

> Triage rules and agent instructions are only the starting point; feedback (`make teach`) refines them later.  

## 3. Notifications

### Telegram bot (recommended, your phone notifies you)

1. In Telegram open [@BotFather](https://t.me/BotFather), send `/newbot`, choose a name and a username ending in `bot`.
2. Copy the token BotFather sends (looks like `123456789:AA...`).
3. Open your new bot (link in BotFather's reply) and press **Start**; a bot can only write to people who started it.
4. Here, choose channel `telegram` and paste the token into **Telegram bot token**.
5. Press **Detect Telegram chat id** and pick your chat; the chat id fills in.
6. Turn **Dry run** off if notifications should really be sent, then press **Save**.
7. Press **Test telegram**; you should receive a test message from your bot.

> Detect finds nothing? Send the bot any message and detect again (Telegram keeps updates for 24 hours).  
> If the token was ever shared (e.g. pasted in a chat), regenerate it in BotFather with `/revoke` and paste the new one.  

### Telegram Saved Messages (optional private log, no phone alert)

1. Go to [my.telegram.org](https://my.telegram.org), log in with your phone, open **API development tools** and create an app (any name).
2. Here, choose channel `telegram_self` and fill in **api_id**, **api_hash** and your phone with `+`.
3. Press **Send login code**; Telegram sends a code to your Telegram app.
4. Enter the code (and your two-step verification password if you use one) and press **Log in**.
5. Press **Save**, then **Test telegram (self)**; the message appears in Saved Messages.

> This login gives the app access to your Telegram account; it is stored encrypted. Log out here to remove it.  

## 4. Gmail

### 1 · Create a Google Cloud project and enable the Gmail API

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project (or pick an existing one).
2. Open [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and press **Enable**.
3. If you will use Calendar, also enable the [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com).

### 2 · Configure the consent screen and add yourself as a test user

1. Open [Google Auth Platform](https://console.cloud.google.com/auth/overview) (older consoles call it **OAuth consent screen**) and press **Get started**.
2. Give the app a name and your email, choose audience **External**, and finish.
3. Under [Audience](https://console.cloud.google.com/auth/audience), add the Gmail address you will connect to **Test users**.

> While the app is in "Testing", only test users can sign in, and Google may ask you to reconnect every 7 days.  

### 3 · Create the OAuth client

1. Open [Clients / Credentials](https://console.cloud.google.com/auth/clients) and press **Create client**.
2. For the **Connect Google** button in this UI: choose **Web application** and add `http://localhost:8000/api/gmail/oauth/callback` under **Authorized redirect URIs**.
3. Alternatively choose **Desktop app** (no redirect URI to enter) and connect from the terminal with `make gmail-auth`.
4. Press **Create**, then **Download JSON**.

> The redirect URI must match exactly, including `http`, port `8000` and the path; it is shown above on this page.  

### 4 · Connect your account

1. Press **Upload client JSON** and choose the downloaded file.
2. Press **Connect Google** (Web client) or run `make gmail-auth` in a terminal (Desktop client).
3. Google warns "Google hasn't verified this app": press **Advanced → Go to (your app)**; it is your own app.
4. Allow the Gmail permission; you return here with "Google account connected".
5. Press **Test connection**; it shows your address and unread count.
6. Choose the **Approval mode** (start with `draft_only`) and press **Save**.

### 5 · Handle new mail automatically

1. Under **Watch for new mail**, switch on **Handle new emails automatically**.
2. Send yourself a test email; within the check interval (`Poll seconds`) it appears in the list with its decision, and a Telegram message arrives if notifications are on.
3. Press **Check now** to check immediately instead of waiting.

> Only emails that arrive after you switch it on are handled, each exactly once (also after a restart).  
> It runs while the app runs. `make worker` runs the same watcher without the UI; only one of them works at a time.  
> Nothing is changed in Gmail; what happens to replies depends on the **Approval mode**.  

### 6 · Include the Spam folder (optional)

1. Turn on **Include spam** in the form above and press **Save**; `Spam query` chooses which Spam emails are checked (default unread).
2. A Spam email the assistant thinks is genuine arrives on Telegram marked "⚠️ From your Spam folder"; ignored ones appear in the digest marked "(spam)".
3. If it is genuine, tap **📥 Not spam**; the email moves to your Inbox and similar emails will be reported next time.

> Spam emails are never answered, whatever the triage decides; Spam is often phishing.  
> **📥 Not spam** is the only change the app ever makes in Gmail, and only when you tap it.  

### Troubleshooting

1. **Watcher shows "Another watcher is handling this mailbox"**: `make worker` or a second copy of the app is running; stop one.
2. **Error 400: redirect_uri_mismatch**: your client is a Desktop app, or the Web client lacks the exact redirect URI. Add it to a Web client, or use `make gmail-auth` with the Desktop client.
3. **Error 403: access_denied** / "has not completed the Google verification process": add your address under **Audience → Test users**.
4. **Test connection fails with "Gmail API has not been used in project"**: enable the Gmail API (section 1) and retry after a minute.
5. **invalid_grant / token expired**: press **Reconnect Google** (test-mode tokens expire after 7 days).

## 5. Calendar

### Use Google Calendar (optional)

1. Enable the [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) in the same Google Cloud project.
2. Turn **Enabled** on here and press **Save**.
3. Go back to the Gmail step and press **Reconnect Google** so the calendar permission is granted.

> Until calendar tools are built, availability is simulated from your working hours.  

## 6. Model

### Local model (Ollama)

1. Install [Ollama](https://ollama.com/download) and pull a model with tool calling, e.g. `ollama pull gemma4:e4b`.
2. Choose provider **Local (Ollama)**; installed models are listed automatically with their capabilities.
3. Pick a model, press **Test this model**; both checks must pass. Then press **Save**.

> If the structured-output check fails, try another model or switch **Reasoning** on/off.  

### API model

1. Create an API key: [Anthropic](https://console.anthropic.com/settings/keys), [OpenAI](https://platform.openai.com/api-keys) or [Google AI Studio](https://aistudio.google.com/apikey); for an OpenAI-compatible server use its URL and key.
2. Choose the provider, paste the key into **Api key**, press **Load available models** and pick one.
3. Press **Test this model**, then **Save**.

> Email content is sent to the provider when an API model is used.  

## 7. Embeddings

### Choose the embedding model

1. Local: `ollama pull nomic-embed-text`, choose provider **Local (Ollama)** and the model.
2. Press **Test embeddings**; if the dimensions differ, press **Use N dimensions**. Then **Save**.

> Memories are stored with these vectors; changing model or dimensions later means existing memories must be re-indexed.  

## 8. Review

### Try it out

1. Press **Dry run on sample emails**; triage accuracy should be close to 100%.
2. With Gmail connected, press **Run on my latest Gmail emails** (read-only; nothing is marked read or sent).
3. Check Telegram for the summaries if notifications are on.

> Runs are tracked in [MLflow](http://localhost:5000) and traced in [Langfuse](http://localhost:3000); `docs/LANGFUSE.md` lists the metrics to watch.  

### Watch how it's doing

1. Open **Visualizations** in the side menu for the headline numbers (feedback, triage mix, cost, latency, tokens, warnings).
2. Below them, the full Langfuse UI is embedded; log in once with the Langfuse account from `.env` if it asks.
3. `docs/LANGFUSE.md` explains every number and what to do when one drifts.

### Give feedback (teaches the assistant)

1. Under each Telegram notification: `ignore · notify · respond` with ✓ on the current decision, then 👍 · 👎 · ✍️ feedback. The daily digest has one such row per ignored email.
2. Tap another label to correct the decision (similar emails will follow it); tap the ticked label or 👍 to confirm it.
3. ✍️ feedback: reply to the bot with what should change; it rewrites the assistant's instructions.
4. The **Feedback** page shows every handled email, its rating and which memory each feedback changed; you can rate there too.

> Feedback is only accepted from your configured chat id.  
> Set the digest time and turn it on/off in Notifications; **Send ignored digest now** on the Feedback page sends it immediately.
