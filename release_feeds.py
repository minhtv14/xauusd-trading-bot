"""Parse the timed releases in the official BLS and BEA iCalendar feeds."""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


RELEASE_FEEDS = {
    "BLS": "https://www.bls.gov/schedule/news_release/bls.ics",
    "BEA": "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics",
}


def load_release_feed(source, fetch):
    """Return sorted (UTC datetime, title) tuples from one agency's calendar."""
    content = fetch(RELEASE_FEEDS[source]).strip("\ufeff\r\n \t")
    lines = re.sub(r"\r?\n[ \t]", "", content).splitlines()
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError(f"{source} calendar is not a complete iCalendar file")

    events = set()
    components = ["VCALENDAR"]
    properties = {}
    for line in lines[1:-1]:
        field, separator, value = line.partition(":")
        if not line:
            continue
        if not separator:
            raise ValueError(f"Malformed field in {source} calendar")
        if field == "BEGIN":
            if value == "VEVENT" and components != ["VCALENDAR"]:
                raise ValueError(f"Unexpected event in {source} calendar")
            components.append(value)
        elif field == "END":
            if len(components) == 1 or components.pop() != value:
                raise ValueError(f"Mismatched components in {source} calendar")
            if value == "VEVENT":
                event = _parse_event(properties, source)
                if event is not None:
                    events.add(event)
                properties.clear()
        elif components == ["VCALENDAR", "VEVENT"]:
            name = field.split(";", 1)[0]
            if name in {"DTSTART", "SUMMARY", "STATUS", "RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"}:
                if name in properties:
                    raise ValueError(f"Duplicate {name} in {source} calendar event")
                properties[name] = (field, value)

    if components != ["VCALENDAR"] or not events:
        raise ValueError(f"{source} calendar has no usable timed events or is incomplete")
    return sorted(events)


def _parse_event(properties, source):
    status = properties.get("STATUS", (None, ""))[1]
    if status == "CANCELLED":
        return None
    field, stamp = properties.get("DTSTART", ("", ""))
    if re.fullmatch(r"[0-9]{8}", stamp):
        datetime.strptime(stamp, "%Y%m%d")
        return None  # Calendar holidays can have dates without release times.
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z?", stamp):
        raise ValueError(f"Missing or invalid start time in {source} calendar event")
    if properties.keys() & {"RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"}:
        raise ValueError(f"Unexpected recurrence in {source} calendar event")

    summary = properties.get("SUMMARY", (None, ""))[1]
    title = re.sub(r"\\([,;\\nN])", lambda match: " " if match[1] in "nN" else match[1], summary).strip()
    if not title:
        raise ValueError(f"Missing title in {source} calendar event")

    when = datetime.strptime(stamp.rstrip("Z"), "%Y%m%dT%H%M%S")
    if stamp.endswith("Z"):
        return when.replace(tzinfo=timezone.utc), title
    zone = re.search(r";TZID=([^;]+)", field)
    if zone is not None and zone[1].strip('"') not in {"America/New_York", "US-Eastern", "US/Eastern"}:
        raise ValueError(f"Unexpected time zone in {source} calendar event")
    return when.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc), title
