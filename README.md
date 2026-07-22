# honest-gmail-mcp

Local Gmail MCP server. Your emails never leave your machine except to Google. No third party in the middle.

## Why this exists

Most Gmail integrations for AI assistants — including the "official" MCP connectors — route your emails through a third-party server before they reach the AI. That means the third party sees plaintext of every message you search, read, or send.

This project takes a different path: it runs on **your** machine, authenticates directly to Google Gmail API with **your** OAuth credentials, and exposes 6 tools to your local AI client (Claude Code, Claude Desktop, or any MCP-compatible client) over stdio.

**Data flow:** `You ↔ this server (on your Mac) ↔ Google Gmail API`. That's the whole path. No hosted service. No proxy. No third-party access to your inbox.

**You can read the entire server** — one file, ~240 lines of Python — and confirm for yourself.

## Features

Six tools exposed over MCP:

- `search_messages` — Gmail search syntax (e.g. `from:foo@bar is:unread newer_than:7d`)
- `get_message` — full headers + decoded text/plain body
- `send_message` — with optional local file attachments (this is a feature the official connector lacks)
- `create_draft` — same fields as send, does not send
- `list_labels` — all labels with ids
- `modify_labels` — add/remove labels on a message

## Requirements

- Python 3.10+
- A Google account you want to give it access to
- A one-time setup in Google Cloud Console (~10 min)

## Setup

### 1. Clone

```bash
git clone https://github.com/bartosz-kuc/honest-gmail-mcp.git
cd honest-gmail-mcp
```

### 2. Install dependencies

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 3. Get Google OAuth credentials

You create your own OAuth client in your own Google Cloud project. Nobody but you controls it.

1. Go to https://console.cloud.google.com/ (signed in with the account you want to authorize)
2. Create a new project (name it whatever, e.g. `gmail-mcp`)
3. **APIs & Services → Library** → search **Gmail API** → **Enable**
4. **APIs & Services → OAuth consent screen**:
   - User Type: **External** → Create
   - App name: `gmail-mcp`
   - User support email + Developer contact: your email
   - Test users: add the email you'll authorize
5. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download the JSON
6. Save it as `credentials.json` in this repo's root directory

### 4. First run (does the OAuth dance)

```bash
./venv/bin/python server.py
```

A browser tab will open. Sign in, click **Allow**. Token is saved locally as `token.json`. The server then starts serving MCP over stdio (nothing visible — it's designed to be launched by an MCP client, not run manually).

You can press Ctrl+C after the browser flow finishes — the token is saved.

### 5. Register with your MCP client

**Claude Code:**

```bash
claude mcp add gmail-personal /absolute/path/to/venv/bin/python /absolute/path/to/server.py
```

**Claude Desktop:** edit `claude_desktop_config.json` (find via Claude menu → Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "gmail-personal": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

Restart the client. Tools appear as `mcp__gmail-personal__search_messages` etc.

## Data flow (in detail)

```
Your AI client (Claude Code / Claude Desktop)
         ↕  MCP protocol over stdio (local process pipe)
This server (Python, on your machine)
         ↕  HTTPS to googleapis.com
Google Gmail API
```

No cloud in the middle. No telemetry. No analytics. The server has no network dependencies beyond Google itself.

The `credentials.json` (your OAuth client secret) and `token.json` (your refresh token) stay on your disk. Both are `.gitignore`d so a stray `git push` cannot leak them.

## Security notes

- **You own the OAuth client.** Nobody else can revoke, rotate, or misuse it.
- **You can revoke access anytime** at https://myaccount.google.com/permissions.
- **Scope requested:** `gmail.modify` — covers read, labels, send, drafts. It does **not** cover Gmail settings, filters, delegates, or account management.
- **No secrets are in git.** `.gitignore` blocks `credentials.json`, `token.json`, and virtualenvs.
- **Audit the code.** `server.py` is ~240 lines. Read it once and you know exactly what it can and cannot do.

## Author

**Bartosz Kuć** — Warsaw-based developer, JDG owner running skanfirmy.pl.

- Site: https://skanfirmy.pl
- GitHub: https://github.com/bartosz-kuc

- Email: firma@bartosza.pl

## Consulting

Available for consulting on Polish tax and business integrations (KSeF, GUS/NFZ/GIOŚ APIs, mBank data), MCP server design, and AI-assisted tooling for JDGs and small teams. Reach out via email.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. Please keep the code minimal and auditable — the whole selling point is that a user can read it in one sitting.
