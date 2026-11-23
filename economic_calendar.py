import logging
import os
from datetime import datetime, time as day_time, timedelta, timezone
from pathlib import Path
from time import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from fed_calendar import load_fed_calendar
from release_feeds import load_release_feed


EASTERN = ZoneInfo("America/New_York")
SOURCES = ("BLS", "BEA", "Fed")
RETRY_INTERVAL = timedelta(minutes=1)
BLS_FILE_MAX_AGE = 24 * 60 * 60


def fetch_calendar(url):
    request = Request(url, headers={"User-Agent": "XAUUSDTradingBot/1.0 (economic calendar)"})
    with urlopen(request, timeout=10) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8-sig")


def load_source(source, first_day, last_day):
    if source == "Fed":
        events = load_fed_calendar(fetch_calendar, first_day, last_day)
    else:
        try:
            events = load_release_feed(source, fetch_calendar)
        except (OSError, ValueError) as error:
            local_file = os.getenv("BLS_CALENDAR_FILE") if source == "BLS" else None
            if not local_file:
                raise
            path = Path(local_file)
            if not 0 <= time() - path.stat().st_mtime <= BLS_FILE_MAX_AGE:
                raise ValueError("Download a fresh official BLS calendar for BLS_CALENDAR_FILE") from error
            events = load_release_feed(source, lambda url: path.read_text(encoding="utf-8-sig"))
            logging.warning("BLS download failed (%s). Using the local BLS calendar file.", error)
        if events[-1][0].astimezone(EASTERN).date() < last_day:
            raise ValueError("Calendar does not cover the required dates")
    return sorted((when.astimezone(timezone.utc), source, title) for when, title in events)


class EconomicCalendar:
    def __init__(self, executor, before_minutes, after_minutes):
        self.executor = executor
        self.before = timedelta(minutes=before_minutes)
        self.after = timedelta(minutes=after_minutes)
        self.events = {}
        self.pending = {}
        self.refresh_at = {}
        self.valid_until = {}

    def poll(self):
        now = datetime.now(timezone.utc)
        tomorrow = now.astimezone().date() + timedelta(days=1)
        next_midnight = datetime.combine(tomorrow, day_time.min).astimezone(timezone.utc)

        for source in SOURCES:
            if source in self.pending and self.pending[source][0].done():
                future, scheduled_refresh = self.pending.pop(source)
                try:
                    events = future.result()
                except Exception as exc:
                    self.valid_until.pop(source, None)
                    self.refresh_at[source] = now + RETRY_INTERVAL
                    logging.warning("%s calendar unavailable. New orders paused. %s", source, exc)
                else:
                    upcoming = next((event for event in events if event[0] >= now), None)
                    if upcoming:
                        when, _, title = upcoming
                        logging.info("%s calendar loaded. Next release: %s at %s", source, title,
                                     when.astimezone().isoformat(timespec="minutes"))
                    else:
                        logging.info("%s calendar loaded.", source)
                    self.events[source] = events
                    self.valid_until[source] = scheduled_refresh + RETRY_INTERVAL
                    self.refresh_at[source] = scheduled_refresh

            if source not in self.pending and now >= self.refresh_at.get(source, now):
                first_day = (now - self.after).astimezone(EASTERN).date()
                horizon = next_midnight + self.before + RETRY_INTERVAL
                last_day = horizon.astimezone(EASTERN).date()
                future = self.executor.submit(load_source, source, first_day, last_day)
                self.pending[source] = (future, next_midnight)

        ready = all(now < self.valid_until.get(source, now) for source in SOURCES)
        active = tuple(sorted(
            event for events in self.events.values() for event in events
            if event[0] - self.before <= now < event[0] + self.after
        ))
        return ready, active
