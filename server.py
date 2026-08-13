"""honest-gmail-mcp — minimal Gmail MCP server for a single Google account.

Exposes 6 tools over MCP stdio: search_messages, get_message, send_message,
create_draft, list_labels, modify_labels. Refresh token stored locally in
token.json next to this file. Attachments accepted as absolute local paths.

Author: Bartosz Kuć <firma@bartosza.pl>
Repo:   https://github.com/bartosz-kuc/honest-gmail-mcp
License: MIT
"""

import asyncio
import base64
import json
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# gmail.modify covers read + labels + send + drafts in one scope.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

HERE = Path(__file__).parent
CRED_PATH = HERE / "credentials.json"
TOKEN_PATH = HERE / "token.json"


def get_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


server = Server("gmail-personal")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_messages",
            description="Search Gmail using Gmail search syntax (e.g. 'from:foo@bar is:unread newer_than:7d'). Returns list of messages with subject/from/date/snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 20, "maximum": 100},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_message",
            description="Fetch full message by id: headers plus decoded text/plain body.",
            inputSchema={
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
        ),
        Tool(
            name="send_message",
            description=(
                "Send an email. Optionally attach local files by absolute path. "
                "To reply inside an existing conversation, pass reply_to_message_id "
                "(the id of the message you are replying to): the mail is threaded "
                "properly (In-Reply-To/References + Gmail threadId), and 'to'/'subject' "
                "default to the original sender and 'Re: <original subject>'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {"type": "string"},
                    "bcc": {"type": "string"},
                    "reply_to_message_id": {
                        "type": "string",
                        "description": "Id of the message to reply to. Makes 'to' and 'subject' optional.",
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths of files to attach.",
                    },
                },
                "required": ["body"],
            },
        ),
        Tool(
            name="create_draft",
            description="Create a draft (same fields as send_message, including reply_to_message_id). Does not send.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {"type": "string"},
                    "bcc": {"type": "string"},
                    "reply_to_message_id": {
                        "type": "string",
                        "description": "Id of the message to reply to. Makes 'to' and 'subject' optional.",
                    },
                    "attachments": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["body"],
            },
        ),
        Tool(
            name="list_labels",
            description="List all Gmail labels with their ids.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="modify_labels",
            description="Add and/or remove labels on a message. Use label ids from list_labels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "add": {"type": "array", "items": {"type": "string"}},
                    "remove": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["message_id"],
            },
        ),
    ]


def _build_mime(to, subject, body, cc="", bcc="", attachments=None, extra_headers=None):
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for path in attachments:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(path)}"',
            )
            msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    for key, value in (extra_headers or {}).items():
        msg[key] = value
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def _reply_context(svc, message_id):
    """Threading info for a reply: headers, thread id, and to/subject defaults."""
    orig = svc.users().messages().get(
        userId="me",
        id=message_id,
        format="metadata",
        # Both spellings requested — providers vary between Message-ID and Message-Id.
        metadataHeaders=["Message-ID", "Message-Id", "References", "Subject", "From", "Reply-To"],
    ).execute()
    headers = {h["name"].lower(): h["value"] for h in orig.get("payload", {}).get("headers", [])}
    orig_msg_id = headers.get("message-id", "")
    references = " ".join(x for x in (headers.get("references", ""), orig_msg_id) if x)
    subject = headers.get("subject", "")
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    extra_headers = {}
    if orig_msg_id:
        extra_headers["In-Reply-To"] = orig_msg_id
    if references:
        extra_headers["References"] = references
    return {
        "thread_id": orig["threadId"],
        "extra_headers": extra_headers,
        "default_to": headers.get("reply-to") or headers.get("from", ""),
        "default_subject": subject,
    }


def _prepare_outgoing(svc, arguments):
    """Build the Gmail API message body for send/draft, resolving reply threading."""
    to = arguments.get("to", "")
    subject = arguments.get("subject", "")
    extra_headers = None
    thread_id = None
    if arguments.get("reply_to_message_id"):
        ctx = _reply_context(svc, arguments["reply_to_message_id"])
        thread_id = ctx["thread_id"]
        extra_headers = ctx["extra_headers"]
        to = to or ctx["default_to"]
        subject = subject or ctx["default_subject"]
    if not to or not subject:
        raise ValueError("'to' and 'subject' are required when reply_to_message_id is not given")
    message = _build_mime(
        to, subject, arguments["body"],
        arguments.get("cc", ""), arguments.get("bcc", ""),
        arguments.get("attachments"), extra_headers,
    )
    if thread_id:
        message["threadId"] = thread_id
    return message


def _decode_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            # Padding suffix: urlsafe base64 sometimes omits padding; extra "===" is harmless.
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        result = _decode_body(part)
        if result:
            return result
    return ""


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    svc = get_service()

    if name == "search_messages":
        listing = svc.users().messages().list(
            userId="me",
            q=arguments["query"],
            maxResults=arguments.get("max_results", 20),
        ).execute()
        out = []
        for m in listing.get("messages", []):
            full = svc.users().messages().get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            out.append({
                "id": m["id"],
                "threadId": m["threadId"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]

    if name == "get_message":
        msg = svc.users().messages().get(
            userId="me", id=arguments["message_id"], format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return [TextContent(type="text", text=json.dumps({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "labelIds": msg.get("labelIds", []),
            "headers": {k: headers.get(k) for k in ("From", "To", "Cc", "Subject", "Date")},
            "body": _decode_body(msg.get("payload", {})),
        }, ensure_ascii=False, indent=2))]

    if name == "send_message":
        raw = _prepare_outgoing(svc, arguments)
        sent = svc.users().messages().send(userId="me", body=raw).execute()
        return [TextContent(type="text", text=json.dumps(
            {"id": sent["id"], "threadId": sent["threadId"]}
        ))]

    if name == "create_draft":
        raw = _prepare_outgoing(svc, arguments)
        draft = svc.users().drafts().create(userId="me", body={"message": raw}).execute()
        return [TextContent(type="text", text=json.dumps(
            {"draft_id": draft["id"], "message_id": draft["message"]["id"], "threadId": draft["message"].get("threadId")}
        ))]

    if name == "list_labels":
        labels = svc.users().labels().list(userId="me").execute().get("labels", [])
        return [TextContent(type="text", text=json.dumps(labels, ensure_ascii=False, indent=2))]

    if name == "modify_labels":
        body = {}
        if arguments.get("add"):
            body["addLabelIds"] = arguments["add"]
        if arguments.get("remove"):
            body["removeLabelIds"] = arguments["remove"]
        result = svc.users().messages().modify(
            userId="me", id=arguments["message_id"], body=body
        ).execute()
        return [TextContent(type="text", text=json.dumps(
            {"id": result["id"], "labelIds": result.get("labelIds", [])}
        ))]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def sync_main():
    """Sync entry point for console script."""
    asyncio.run(main())


if __name__ == "__main__":
    sync_main()
