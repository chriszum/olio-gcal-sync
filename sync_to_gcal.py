#!/usr/bin/env python3
"""
Syncs Olio events from Viewcy API to Google Calendar.
Run once to add all current events; re-running skips duplicates by checking event description for the Viewcy UUID.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

VIEWCY_URL = "https://www.viewcy.com/api/v1/schools/olio/courses"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

# Change this to the name of the calendar you want to add events to.
# Use "primary" for your main calendar, or the exact name of another calendar.
CALENDAR_NAME = "Olio Events"


def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"ERROR: {CREDENTIALS_FILE} not found.")
                print("Download it from: https://console.cloud.google.com/apis/credentials")
                print("Create an OAuth 2.0 Client ID (Desktop app), download the JSON, save as credentials.json")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def get_or_create_calendar(service, name):
    calendars = service.calendarList().list().execute()
    for cal in calendars.get("items", []):
        if cal["summary"] == name:
            return cal["id"]
    # Create it
    new_cal = service.calendars().insert(body={"summary": name, "timeZone": "America/New_York"}).execute()
    print(f"Created calendar: {name}")
    return new_cal["id"]


def get_existing_event_ids(service, calendar_id):
    """Returns a set of Viewcy event UUIDs already in the calendar."""
    existing = set()
    page_token = None
    while True:
        result = service.events().list(
            calendarId=calendar_id,
            pageToken=page_token,
            privateExtendedProperty="viewcy_uuid=*",
        ).execute()
        for event in result.get("items", []):
            uid = event.get("extendedProperties", {}).get("private", {}).get("viewcy_uuid")
            if uid:
                existing.add(uid)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return existing


def strip_html(html):
    return re.sub(r"<[^>]+>", "", html).strip()


def fetch_viewcy_events():
    resp = requests.get(VIEWCY_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()


def create_calendar_event(course, event):
    starts_at = event["starts_at"]  # e.g. "2026-04-09T23:30:00.000Z"
    ends_at = event["ends_at"]

    description_text = strip_html(course.get("description", ""))
    book_url = event.get("book_url", course.get("url", ""))
    if book_url:
        description_text = f"{description_text}\n\nTickets & info: {book_url}".strip()

    return {
        "summary": course["name"],
        "description": description_text,
        "start": {"dateTime": starts_at, "timeZone": course.get("timezone", "America/New_York")},
        "end": {"dateTime": ends_at, "timeZone": course.get("timezone", "America/New_York")},
        "source": {"title": "Viewcy", "url": book_url} if book_url else None,
        "extendedProperties": {
            "private": {
                "viewcy_uuid": event["uuid"],
                "viewcy_course_uuid": course["uuid"],
            }
        },
    }


def main():
    print("Fetching Viewcy events...")
    courses = fetch_viewcy_events()
    print(f"Found {len(courses)} courses")

    print("Connecting to Google Calendar...")
    service = get_calendar_service()
    calendar_id = get_or_create_calendar(service, CALENDAR_NAME)
    print(f"Using calendar: {CALENDAR_NAME} ({calendar_id})")

    existing_uuids = get_existing_event_ids(service, calendar_id)
    print(f"Already synced: {len(existing_uuids)} events")

    added = 0
    skipped = 0
    for course in courses:
        for event in course.get("events", []):
            uid = event["uuid"]
            if uid in existing_uuids:
                skipped += 1
                continue
            body = create_calendar_event(course, event)
            service.events().insert(calendarId=calendar_id, body=body).execute()
            print(f"  Added: {course['name']} ({event['starts_at'][:10]})")
            added += 1

    print(f"\nDone. Added: {added}, Skipped (already exists): {skipped}")


if __name__ == "__main__":
    main()
