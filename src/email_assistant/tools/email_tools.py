"""Email and calendar tools for the response agent.

Simulated for now: nothing is sent or booked, the agent only gets a confirmation
back. Availability is derived from the profile's working hours and scheduling
settings. The Gmail / Calendar backed versions replace these when the worker is built.
"""

from datetime import datetime, timedelta

from langchain_core.tools import BaseTool, tool

from email_assistant.profile import Profile

# Notifications look for this tool's calls to report what was sent
WRITE_EMAIL = "write_email"


def _free_slots(profile: Profile) -> list[str]:
    hours, sched = profile.user.working_hours, profile.scheduling
    start = datetime.strptime(hours.start, "%H:%M")
    end = datetime.strptime(hours.end, "%H:%M")
    meeting = timedelta(minutes=sched.default_meeting_minutes)
    step = meeting + timedelta(minutes=sched.buffer_minutes)
    slots = []
    while start + meeting <= end:
        slots.append(start.strftime("%H:%M"))
        start += step
    return slots


def email_tools(profile: Profile) -> list[BaseTool]:
    @tool(WRITE_EMAIL)
    def write_email(to: str, subject: str, content: str) -> str:
        """Write and send an email."""
        return f"Email sent to {to} with subject '{subject}'"

    @tool
    def schedule_meeting(attendees: list[str], subject: str, duration_minutes: int, preferred_day: str,
                         start_time: str) -> str:
        """Book a meeting on a day at a start time (HH:MM) returned by check_calendar_availability."""
        if start_time not in _free_slots(profile):
            return (f"Not booked: {start_time} is not a free start time. "
                    f"Free start times: {', '.join(_free_slots(profile))}.")
        end = datetime.strptime(start_time, "%H:%M") + timedelta(minutes=duration_minutes)
        return (f"Booked '{subject}' on {preferred_day} {start_time}-{end:%H:%M} ({profile.user.timezone}) "
                f"with {', '.join(attendees)}")

    @tool
    def check_calendar_availability(day: str) -> str:
        """Check calendar availability for a given day."""
        sched = profile.scheduling
        blocked = f" Never schedule: {', '.join(sched.no_meetings)}." if sched.no_meetings else ""
        return (
            f"Available start times on {day} ({profile.user.timezone}): {', '.join(_free_slots(profile))}. "
            f"Working days: {', '.join(profile.user.working_hours.days)}.{blocked}"
        )

    return [write_email, schedule_meeting, check_calendar_availability]
