import os
import pickle
from datetime import datetime, timezone
from typing import Optional

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

TOKEN_FILE = os.getenv("TOKEN_FILE", "/app/credentials/token.pickle")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "/app/credentials/client_secrets.json")


class GoogleCalendarService:
    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None

        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                with open(TOKEN_FILE, "wb") as f:
                    pickle.dump(creds, f)
            else:
                raise PermissionError(
                    "Not authenticated with Google. "
                    "Visit http://localhost:8000/login in your browser to authorize access."
                )

        return build("calendar", "v3", credentials=creds)

    def list_calendars(self) -> list[dict]:
        result = self.service.calendarList().list().execute()
        return [
            {
                "id": c["id"],
                "summary": c.get("summary", "Untitled"),
                "primary": c.get("primary", False),
                "access_role": c.get("accessRole"),
                "time_zone": c.get("timeZone"),
            }
            for c in result.get("items", [])
        ]

    def list_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> list[dict]:
        if time_min is None:
            time_min = datetime.now(timezone.utc).isoformat()

        params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            params["timeMax"] = time_max

        result = self.service.events().list(**params).execute()
        return [
            {
                "id": e["id"],
                "summary": e.get("summary", "No title"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
                "description": e.get("description"),
                "location": e.get("location"),
                "attendees": [a["email"] for a in e.get("attendees", [])],
                "link": e.get("htmlLink"),
                "status": e.get("status"),
            }
            for e in result.get("items", [])
        ]

    def get_event(self, event_id: str, calendar_id: str = "primary") -> dict:
        e = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return {
            "id": e["id"],
            "summary": e.get("summary", "No title"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "description": e.get("description"),
            "location": e.get("location"),
            "attendees": [a["email"] for a in e.get("attendees", [])],
            "link": e.get("htmlLink"),
            "status": e.get("status"),
        }

    def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        time_zone: str = "UTC",
        calendar_id: str = "primary",
    ) -> dict:
        body: dict = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": time_zone},
            "end": {"dateTime": end_datetime, "timeZone": time_zone},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        created = self.service.events().insert(calendarId=calendar_id, body=body).execute()
        return {
            "id": created["id"],
            "summary": created.get("summary"),
            "start": created["start"].get("dateTime", created["start"].get("date")),
            "end": created["end"].get("dateTime", created["end"].get("date")),
            "link": created.get("htmlLink"),
        }

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict:
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id}
