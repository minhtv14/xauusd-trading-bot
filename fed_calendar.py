"""Read timed releases from the Federal Reserve's public monthly calendar."""

import re
from calendar import month_name
from collections.abc import Callable
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.error import HTTPError
from zoneinfo import ZoneInfo


FED_CALENDAR_URL = "https://www.federalreserve.gov/newsevents/{year}-{month}.htm"
RELEASE_SECTIONS = {"FOMC Meetings", "Beige Book", "Statistical Releases"}
RELEASE_COLUMNS = {"col-xs-2": "time", "col-xs-7": "title", "col-xs-3": "days"}


class _FedMonthlyPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.month = ""
        self.releases = []
        self.complete = False
        self._depth = 0
        self._article_depth = None
        self._panel_depth = None
        self._column_depth = None
        self._column = None
        self._section = ""
        self._fields = {}
        self._text = []
        self._title_started = False
        self._title_finished = False

    def handle_starttag(self, tag, attrs):
        if tag == "p" and self._column == "title":
            self._title_started = True
        if tag != "div":
            return
        self._depth += 1
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if attributes.get("id") == "article" and "cal-nojs" in classes:
            self._article_depth = self._depth
        if self._article_depth is None:
            return
        if "row-title" in classes:
            self._start_column("month")
        elif "cal-nojs__rowTitle" in classes:
            self._start_column("section")
        elif "panel-body" in classes and self._section in RELEASE_SECTIONS:
            self._panel_depth = self._depth
            self._fields = {}
        elif self._panel_depth is not None and self._depth == self._panel_depth + 2:
            for column_class, column in RELEASE_COLUMNS.items():
                if column_class in classes:
                    self._start_column(column)
                    break

    def handle_data(self, data):
        if self._column == "title" and (not self._title_started or self._title_finished):
            return
        if self._column is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self._column == "title" and self._title_started:
            self._title_finished = True
        if tag != "div":
            return
        if self._depth == self._column_depth:
            value = " ".join("".join(self._text).split())
            if self._column == "month":
                self.month = value
            elif self._column == "section":
                self._section = value
            else:
                if self._column in self._fields:
                    raise ValueError(f"Duplicate column in Fed {self._section}")
                self._fields[self._column] = value
            self._column_depth = self._column = None
        if self._depth == self._panel_depth:
            if self._fields.keys() != {"time", "title", "days"} or not self._fields["title"]:
                raise ValueError(f"Invalid release row in Fed {self._section}")
            self.releases.append((self._section, self._fields))
            self._panel_depth = None
        if self._depth == self._article_depth:
            self._article_depth = None
            self.complete = True
        self._depth -= 1

    def _start_column(self, name):
        self._column = name
        self._column_depth = self._depth
        self._text = []
        self._title_started = self._title_finished = False


def _parse_month(html, year, month):
    page = _FedMonthlyPage()
    page.feed(html)
    page.close()
    expected_month = f"{month_name[month]} {year}"
    if (
        not page.complete
        or page.month != expected_month
        or not any(section == "Statistical Releases" for section, _ in page.releases)
    ):
        raise ValueError(f"Fed release calendar missing or unreadable for {expected_month}")

    eastern = ZoneInfo("America/New_York")
    for _, release in page.releases:
        # Certain releases (for example, G.20) are listed without an exact time.
        if not release["time"]:
            continue
        time_text = re.sub(r"[\s.]", "", release["time"].lower())
        clock = datetime.strptime(time_text.upper(), "%I:%M%p").time()
        if not re.fullmatch(r"\d{1,2}(?:\s*,\s*\d{1,2})*", release["days"]):
            raise ValueError(f"Invalid release date in Fed calendar for {expected_month}: {release['title']}")
        for day in release["days"].split(","):
            release_date = date(year, month, int(day))
            yield datetime.combine(release_date, clock, eastern), release["title"]


def load_fed_calendar(
    fetch: Callable[[str], str], first_day: date, last_day: date
) -> list[tuple[datetime, str]]:
    """Fetch Fed releases for the inclusive date range, in US Eastern time."""
    releases = []
    month = first_day.replace(day=1)
    while month <= last_day:
        url = FED_CALENDAR_URL.format(year=month.year, month=month_name[month.month].lower())
        try:
            html = fetch(url)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            # Fed uses a numeric month in some archive URLs, including April 2026.
            html = fetch(FED_CALENDAR_URL.format(year=month.year, month=f"{month.month:02d}"))
        releases.extend(
            (when, title)
            for when, title in _parse_month(html, month.year, month.month)
            if first_day <= when.date() <= last_day
        )
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return sorted(releases)
