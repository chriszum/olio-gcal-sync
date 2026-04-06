#!/usr/bin/env python3
"""
Fetches Olio events from Viewcy and writes olio_events.ics.
Uses curl for the HTTP request — no external Python dependencies.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone

VIEWCY_URL = "https://www.viewcy.com/api/v1/schools/olio/courses"
OUTPUT_FILE = "olio_events.ics"


def fetch_courses():
    result = subprocess.run(
        ["curl", "-sf", "--user-agent", "Mozilla/5.0", VIEWCY_URL],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"curl error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    return data["data"]


def strip_html(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def ics_escape(text):
    return (text
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n"))


def fold(line):
    """Fold long lines per RFC 5545 (max 75 octets)."""
    result = []
    while len(line.encode("utf-8")) > 75:
        n = 75
        while len(line[:n].encode("utf-8")) > 75:
            n -= 1
        result.append(line[:n])
        line = " " + line[n:]
    result.append(line)
    return "\r\n".join(result)


def format_dt(iso_str):
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build_ics(courses):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Olio//Viewcy Sync//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Olio Events",
        "X-WR-TIMEZONE:America/New_York",
    ]

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for course in courses:
        for event in course.get("events", []):
            uid = event["uuid"] + "@viewcy.olio"
            summary = ics_escape(course["name"])
            description = ics_escape(strip_html(course.get("description", "")))
            url = event.get("book_url") or course.get("url", "")
            if url:
                description += ("\\n\\nTickets & info: " + url) if description else ("Tickets & info: " + url)

            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now}",
                f"DTSTART:{format_dt(event['starts_at'])}",
                f"DTEND:{format_dt(event['ends_at'])}",
                fold(f"SUMMARY:{summary}"),
                fold(f"DESCRIPTION:{description}"),
            ]
            if url:
                lines.append(f"URL:{url}")
            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    print("Fetching Viewcy events...")
    courses = fetch_courses()
    total = sum(len(c.get("events", [])) for c in courses)
    print(f"Found {len(courses)} courses, {total} events")

    ics = build_ics(courses)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ics)
    print(f"Written: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
