import { Alert, Stack } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { SectionEditor } from "../../components/SectionEditor";

export function CalendarStep() {
  const queryClient = useQueryClient();
  return (
    <Stack>
      <Alert color="blue">
        Calendar uses the same Google sign-in as Gmail. After enabling it, go back to the Gmail step and press
        "Reconnect Google" so the calendar permission is granted.
      </Alert>
      <SectionEditor section="calendar" onSaved={() => queryClient.invalidateQueries({ queryKey: ["gmail-status"] })} />
    </Stack>
  );
}
