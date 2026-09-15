"""Authorize a Google account into a token file for honest-gmail-mcp.

One codebase can serve several Gmail accounts: each account gets its own token
file, and each MCP server instance points at one token via GMAIL_TOKEN_PATH.
This script runs the one-time OAuth consent flow that mints such a token file.

Usage:
    ./venv/bin/python authorize.py <token_filename> [login_hint_email]

Examples:
    ./venv/bin/python authorize.py token.kucio012.json kucio012@gmail.com
    ./venv/bin/python authorize.py token.bartoszkuc7.json bartoszkuc7@gmail.com

Opens a browser for Google consent; sign in with the target account and approve.
The refresh token is written to <token_filename> next to this script (relative
paths are resolved against the script directory). credentials.json (the shared
OAuth client) is used unless GMAIL_CREDENTIALS_PATH overrides it.
"""

import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
HERE = Path(__file__).parent
CRED_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", str(HERE / "credentials.json")))


def main() -> None:
    token_arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GMAIL_TOKEN_PATH", "token.json")
    login_hint = sys.argv[2] if len(sys.argv) > 2 else None

    token_path = Path(token_arg)
    if not token_path.is_absolute():
        token_path = HERE / token_path

    kwargs = {"access_type": "offline", "prompt": "consent"}
    if login_hint:
        kwargs["login_hint"] = login_hint

    flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
    creds = flow.run_local_server(port=0, **kwargs)
    token_path.write_text(creds.to_json())
    print(f"OK: wrote token -> {token_path}")


if __name__ == "__main__":
    main()
