"""Calendar-day schedules anchored across restarts and daylight saving changes."""

import datetime as dt
from zoneinfo import ZoneInfo

from apscheduler.triggers.base import BaseTrigger


class CalendarDaysTrigger(BaseTrigger):
    def __init__(self, *, days, hour, minute, anchor, timezone):
        self.days = int(days)
        if self.days < 1:
            raise ValueError('Schedule days must be positive.')
        self.clock = dt.time(int(hour), int(minute))
        self.anchor = dt.date.fromisoformat(str(anchor))
        self.timezone = ZoneInfo(str(timezone))

    def get_next_fire_time(self, previous_fire_time, now):
        threshold = now.astimezone(dt.timezone.utc)
        if previous_fire_time is not None:
            threshold = max(threshold, previous_fire_time.astimezone(dt.timezone.utc) + dt.timedelta(microseconds=1))
        date = threshold.astimezone(self.timezone).date()
        elapsed = max(0, (date - self.anchor).days)
        date = self.anchor + dt.timedelta(days=((elapsed + self.days - 1) // self.days) * self.days)
        while True:
            candidate = dt.datetime.combine(date, self.clock, self.timezone)
            # A nonexistent spring-forward time runs at the next real local time.
            candidate = candidate.astimezone(dt.timezone.utc).astimezone(self.timezone)
            if candidate.astimezone(dt.timezone.utc) >= threshold:
                return candidate
            date += dt.timedelta(days=self.days)

    def __str__(self):
        return f'Every {self.days} day(s) at {self.clock:%H:%M} ({self.timezone})'
