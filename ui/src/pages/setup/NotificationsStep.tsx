import { Alert, Button, Divider, Group, Select, Stack, Text } from "@mantine/core";
import { IconBrandTelegram, IconSearch } from "@tabler/icons-react";
import { useState } from "react";
import { api, type Check } from "../../api";
import { CheckList } from "../../components/CheckList";
import { SectionEditor, type SectionContext } from "../../components/SectionEditor";
import { TelegramSelfPanel } from "./SelfChannels";

type Chat = { chat_id: number; name: string };

function Actions({ value, setValue, save, secretValues }: SectionContext) {
  const [chats, setChats] = useState<Chat[] | null>(null);
  const [results, setResults] = useState<Record<string, Check>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const detect = () =>
    run("detect", async () => {
      // store a freshly typed token on its own: the form can't be saved until the chat id is known
      if (secretValues.telegram_bot_token) {
        await api.put("/config/notifications/secrets", { secrets: { telegram_bot_token: secretValues.telegram_bot_token } });
      }
      setChats(await api.get<Chat[]>("/notifications/telegram/chats"));
    });

  const test = (channel: string) =>
    run(channel, async () => {
      await save();
      const r = await api.post<{ ok: boolean; detail: string }>("/notifications/test", { channel });
      setResults((prev) => ({ ...prev, [channel]: r }));
    });

  return (
    <Stack>
      {value.channels?.includes("telegram_self") && <TelegramSelfPanel save={save} />}
      <Divider label="Connection tests" labelPosition="left" />
      <Text size="sm" c="dimmed">
        Tests save the form first, then really send one message (even in dry-run mode).
      </Text>
      <Group>
        <Button variant="light" leftSection={<IconSearch size={16} />} loading={busy === "detect"} onClick={detect}>
          Detect Telegram chat id
        </Button>
        {(["telegram", "telegram_self"] as const).map((ch) => (
          <Button key={ch} variant="light" loading={busy === ch} disabled={!value.channels?.includes(ch)} onClick={() => test(ch)}
                  leftSection={<IconBrandTelegram size={16} />}>
            Test {ch.replace("_self", " (self)")}
          </Button>
        ))}
      </Group>
      {chats && (chats.length ? (
        <Select label="Chats that messaged your bot" placeholder="Pick your chat"
                data={chats.map((c) => ({ value: String(c.chat_id), label: `${c.name ?? "chat"} (${c.chat_id})` }))}
                onChange={(id) => id && setValue({ ...value, telegram_chat_id: id })}
                description="Then press Save" />
      ) : (
        <Alert color="yellow">No chats yet: open your bot in Telegram, send /start, then detect again.</Alert>
      ))}
      {error && <Alert color="red">{error}</Alert>}
      {Object.keys(results).length > 0 && <CheckList checks={results} />}
    </Stack>
  );
}

export function NotificationsStep() {
  return (
    <SectionEditor section="notifications"
                   showSecret={(name, v) => {
                     // each secret belongs to one channel
                     const channel = { telegram_bot_token: "telegram", telegram_api_hash: "telegram_self" }[name];
                     return !!channel && v.channels?.includes(channel);
                   }}>
      {(ctx) => <Actions {...ctx} />}
    </SectionEditor>
  );
}
