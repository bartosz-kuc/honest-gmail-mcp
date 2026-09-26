# honest-gmail-mcp

Local Gmail MCP server. Your emails never leave your machine except to Google. No third party in the middle.

## Why this exists

Most Gmail integrations for AI assistants — including the "official" MCP connectors — route your emails through a third-party server before they reach the AI. That means the third party sees plaintext of every message you search, read, or send.

This project takes a different path: it runs on **your** machine, authenticates directly to Google Gmail API with **your** OAuth credentials, and exposes 6 tools to your local AI client (Claude Code, Claude Desktop, or any MCP-compatible client) over stdio.

**Data flow:** `You ↔ this server (on your machine) ↔ Google Gmail API`. That's the whole path. No hosted service. No proxy. No third-party access to your inbox.

**You can read the entire server** — one file, a few hundred lines of Python — and confirm for yourself.

## Features

Six tools exposed over MCP:

- `search_messages` — Gmail search syntax (e.g. `from:foo@bar is:unread newer_than:7d`)
- `get_message` — full headers + decoded text/plain body
- `send_message` — with optional local file attachments (this is a feature the official connector lacks), and proper in-thread replies via `reply_to_message_id` (sets `In-Reply-To`/`References` and Gmail `threadId`; `to`/`subject` default to the original sender and `Re: <subject>`)
- `create_draft` — same fields as send (including replies), does not send
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

On Windows, create the venv with `py -m venv venv` and use `venv\Scripts\pip` / `venv\Scripts\python` in place of the `venv/bin/...` paths shown throughout this README.

### 3. Get Google OAuth credentials

You create your own OAuth client in your own Google Cloud project. Nobody but you controls it.

1. Go to https://console.cloud.google.com/ (signed in with the account you want to authorize)
2. Create a new project (name it whatever, e.g. `honest-gmail-mcp`)
3. **APIs & Services → Library** → search **Gmail API** → **Enable**
4. **APIs & Services → OAuth consent screen**:
   - User Type: **External** → Create
   - App name: `honest-gmail-mcp`
   - User support email + Developer contact: your email
   - Test users: add the email you'll authorize
5. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download the JSON
6. Save it as `credentials.json` in this repo's root directory

### 4. Authorize (one-time OAuth consent)

```bash
./venv/bin/python authorize.py
```

A browser tab will open. Sign in, click **Allow**. The refresh token is saved locally as `token.json` and the script exits.

If you skip this step, the server runs the same browser flow on its first tool call. (`server.py` itself is meant to be launched by an MCP client; started by hand it just waits silently on stdio.)

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

## Multiple Google accounts

One server instance serves one account. For more accounts, register one instance per account (same checkout), each with its own token file, via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GMAIL_TOKEN_PATH` | `token.json` next to `server.py` | Refresh token of the account this instance uses |
| `GMAIL_CREDENTIALS_PATH` | `credentials.json` next to `server.py` | OAuth client JSON; can be shared by all accounts |
| `GMAIL_SERVER_NAME` | `gmail-personal` | Server name the instance reports to the MCP client |

Paths are used as given (no `~` expansion), so use absolute paths.

1. Add the extra address as a test user on the OAuth consent screen (step 3).
2. Mint its token. A relative file name is saved next to `authorize.py`; the optional email pre-selects the account at Google sign-in:

   ```bash
   ./venv/bin/python authorize.py token.work.json you@work.example
   ```

3. Register a second server that points at it, as another entry under `mcpServers` (Claude Desktop config shown; the same entry works in Claude Code's `.mcp.json`):

   ```json
   "gmail-work": {
     "command": "/absolute/path/to/venv/bin/python",
     "args": ["/absolute/path/to/server.py"],
     "env": {
       "GMAIL_TOKEN_PATH": "/absolute/path/to/token.work.json",
       "GMAIL_SERVER_NAME": "gmail-work"
     }
   }
   ```

`.gitignore` covers `token*.json`, so per-account token files are not committed.

## Installing from PyPI (`pip` / `uvx`)

The package contains only the server module (command `honest-gmail-mcp`); `authorize.py` is not included. Default `credentials.json`/`token.json` paths resolve next to the installed module (site-packages or uv's cache), which is no place for secrets and can be wiped on upgrade. Set both variables to absolute paths in an existing directory you own:

```json
"gmail-personal": {
  "command": "uvx",
  "args": ["honest-gmail-mcp"],
  "env": {
    "GMAIL_CREDENTIALS_PATH": "/absolute/path/to/credentials.json",
    "GMAIL_TOKEN_PATH": "/absolute/path/to/token.json"
  }
}
```

If the token file does not exist yet, the server opens the browser consent flow on its first tool call and writes the token to `GMAIL_TOKEN_PATH`.

These variables and the mcp 2.x API need version 0.2.0 or newer; 0.1.0 does not read them and fails to start with mcp 2.x.

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
- **Audit the code.** `server.py` is a few hundred lines. Read it once and you know exactly what it can and cannot do.

## Author

**Bartosz Kuć** — Warsaw-based developer, JDG owner running skanfirmy.pl.

- Site: https://skanfirmy.pl
- GitHub: https://github.com/bartosz-kuc

- Email: firma@bartosza.pl

## Consulting

Available for consulting on Polish tax and business integrations (KSeF, GUS/NFZ/GIOŚ APIs, mBank data), MCP server design, and AI-assisted tooling for JDGs and small teams. See **[skanfirmy.pl/uslugi](https://skanfirmy.pl/uslugi)** for productized packages (audit 3k PLN, setup 8-15k PLN, retainer 2-4k PLN/mo), or reach out via email.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. Please keep the code minimal and auditable — the whole selling point is that a user can read it in one sitting.
