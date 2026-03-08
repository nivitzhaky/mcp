import json
import os
import pickle
import secrets
from typing import Any

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import uvicorn

from calendar_service import GoogleCalendarService, CREDENTIALS_FILE, TOKEN_FILE, SCOPES

load_dotenv()

_api_key = os.environ.get("MCP_API_KEY", "")
if not _api_key:
    raise RuntimeError("MCP_API_KEY environment variable is required")

OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/oauth2callback")
_oauth_states: dict[str, Any] = {}
PUBLIC_PATHS = {"/health", "/login", "/oauth2callback", "/favicon.ico"}

_calendar: GoogleCalendarService | None = None


def get_calendar() -> GoogleCalendarService:
    global _calendar
    if _calendar is None:
        _calendar = GoogleCalendarService()
    return _calendar


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        query_key = request.query_params.get("api_key", "")
        if auth == f"Bearer {_api_key}" or query_key == _api_key:
            return await call_next(request)
        return Response(
            json.dumps({"error": "Unauthorized: provide a valid Bearer token or api_key query param"}),
            status_code=401,
            media_type="application/json",
        )


mcp = FastMCP("Google Calendar MCP", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


@mcp.tool()
def list_calendars() -> list[dict]:
    """List all Google Calendars accessible to the authenticated user."""
    return get_calendar().list_calendars()


@mcp.tool()
def list_events(
    calendar_id: str = "primary",
    max_results: int = 10,
    time_min: str | None = None,
    time_max: str | None = None,
) -> list[dict]:
    """List upcoming events from a Google Calendar.

    Args:
        calendar_id: Calendar ID (default: 'primary')
        max_results: Maximum number of events to return
        time_min: Lower bound for event start time as ISO 8601 string. Defaults to now.
        time_max: Upper bound for event start time as ISO 8601 string.
    """
    return get_calendar().list_events(
        calendar_id=calendar_id,
        max_results=max_results,
        time_min=time_min,
        time_max=time_max,
    )


@mcp.tool()
def get_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Get details of a specific Google Calendar event by ID.

    Args:
        event_id: The event ID
        calendar_id: Calendar ID (default: 'primary')
    """
    return get_calendar().get_event(event_id=event_id, calendar_id=calendar_id)


@mcp.tool()
def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    time_zone: str = "UTC",
    calendar_id: str = "primary",
) -> dict:
    """Create a new event in Google Calendar.

    Args:
        summary: Event title
        start_datetime: Start datetime in ISO 8601 format (e.g. 2026-03-10T14:00:00)
        end_datetime: End datetime in ISO 8601 format (e.g. 2026-03-10T15:00:00)
        description: Event description
        location: Event location
        attendees: List of attendee email addresses
        time_zone: IANA timezone name (default: 'UTC')
        calendar_id: Calendar ID (default: 'primary')
    """
    return get_calendar().create_event(
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees,
        time_zone=time_zone,
        calendar_id=calendar_id,
    )


@mcp.tool()
def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a Google Calendar event by ID.

    Args:
        event_id: The event ID to delete
        calendar_id: Calendar ID (default: 'primary')
    """
    return get_calendar().delete_event(event_id=event_id, calendar_id=calendar_id)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "google_authenticated": os.path.exists(TOKEN_FILE)})


@mcp.custom_route("/login", methods=["GET"])
async def login(request: Request) -> Response:
    if not os.path.exists(CREDENTIALS_FILE):
        return HTMLResponse(_render_error(
            "Missing credentials file",
            f"Place your <code>client_secrets.json</code> from Google Cloud Console at:<br><br>"
            f"<code>{CREDENTIALS_FILE}</code>",
        ), status_code=500)

    flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=OAUTH_REDIRECT_URI)
    state = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(
        state=state,
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _oauth_states[state] = flow
    return RedirectResponse(auth_url)


@mcp.custom_route("/oauth2callback", methods=["GET"])
async def oauth2callback(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    if error:
        return HTMLResponse(_render_error("Google authorization denied", f"Error: <code>{error}</code>"), status_code=400)

    state = request.query_params.get("state", "")
    flow = _oauth_states.pop(state, None)
    if flow is None:
        return HTMLResponse(_render_error(
            "Invalid OAuth state",
            "This link has already been used or is invalid. Visit <a href='/login'>/login</a> to start again.",
        ), status_code=400)

    flow.fetch_token(code=request.query_params.get("code", ""))
    creds = flow.credentials

    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

    global _calendar
    _calendar = None

    email = ""
    try:
        import google.oauth2.id_token
        import google.auth.transport.requests
        id_info = google.oauth2.id_token.verify_oauth2_token(
            creds.id_token, google.auth.transport.requests.Request()
        )
        email = id_info.get("email", "")
    except Exception:
        pass

    return HTMLResponse(_render_success(email))


def _render_success(email: str) -> str:
    account_line = f"<p class='email'>Signed in as <strong>{email}</strong></p>" if email else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Connected — Google Calendar MCP</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f4f8; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
    .card {{ background: white; border-radius: 16px; padding: 48px 40px; max-width: 480px; width: 100%; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .icon {{ font-size: 56px; margin-bottom: 16px; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }}
    .subtitle {{ color: #6b7280; font-size: 15px; margin-bottom: 24px; }}
    .email {{ color: #374151; font-size: 14px; background: #f3f4f6; padding: 10px 16px; border-radius: 8px; margin-bottom: 24px; }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; background: #d1fae5; color: #065f46; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 99px; }}
    .badge::before {{ content: '✓'; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">📅</div>
    <h1>Google Calendar connected</h1>
    <p class="subtitle">Your MCP server can now read and manage your calendar.</p>
    {account_line}
    <span class="badge">Authorization saved</span>
  </div>
</body>
</html>"""


def _render_error(title: str, detail: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Error — Google Calendar MCP</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f4f8; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
    .card {{ background: white; border-radius: 16px; padding: 48px 40px; max-width: 480px; width: 100%; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .icon {{ font-size: 56px; margin-bottom: 16px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #1a1a2e; margin-bottom: 12px; }}
    .detail {{ color: #6b7280; font-size: 14px; line-height: 1.6; }}
    code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
    a {{ color: #4f46e5; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚠️</div>
    <h1>{title}</h1>
    <p class="detail">{detail}</p>
  </div>
</body>
</html>"""


app = mcp.sse_app()
app.add_middleware(APIKeyMiddleware)


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
        reload_dirs=["/app"],
    )
