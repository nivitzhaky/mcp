# MCP Servers

This repo contains a Google Calendar MCP server

---

## Playwright MCP (with VNC browser display)

Uses the [`pranavgade20/browser-sandbox`](https://hub.docker.com/r/pranavgade20/browser-sandbox) image — a pre-built Playwright MCP server with noVNC support. No custom Dockerfile needed.

### Run

```bash
docker run  \
  -p 8931:8931 \
  -p 6080:6080 \
  pranavgade20/browser-sandbox
```

| Port | Purpose |
|------|---------|
| `8931` | Playwright MCP SSE endpoint |
| `6080` | noVNC web viewer |

### View the browser

Open in your browser:
```
http://localhost:6080/vnc.html
```

Click **Connect** to watch browser automation live.

### Cursor MCP Config

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "url": "http://localhost:8931/sse"
    }
  }
}
```

Restart or toggle the MCP server in **Cursor Settings → MCP** to apply.
---

## Google Calendar MCP

### Setup

1. Copy `.env.example` to `.env` and fill in values:
   ```bash
   cp .env.example .env
   ```

2. Set up Google Cloud credentials:
   - **Enable the Calendar API:** https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
   - **Create OAuth 2.0 credentials:** https://console.cloud.google.com/apis/credentials
     - Click **Create Credentials → OAuth client ID**
     - Application type: **Web application**
     - Add `http://localhost:8000/oauth2callback` as an Authorized redirect URI
     - Download the JSON and save it as `credentials/client_secrets.json`

3. Start the server:
   ```bash
   docker compose up --build
   ```

4. Authenticate with Google by visiting:
   ```
   http://localhost:8000/login
   ```

### Cursor MCP Config

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "google-calendar": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer SECURE_API_KEY_HERE"
      }
    }
  }
}
```
