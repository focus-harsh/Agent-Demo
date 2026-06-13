# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Gmail Client
# Handles: labels, email fetching, draft creation
# ──────────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 3A — Label Management
# ═══════════════════════════════════════════════════════════════

def ensure_label_exists(service, label_name: str) -> str:
    """
    Ensure a Gmail label exists. Create it if it doesn't.

    Args:
        service: Gmail API service client.
        label_name: Display name of the label (e.g. "Agent-Processed").

    Returns:
        The label ID (string).
    """
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])

    for label in labels:
        if label["name"] == label_name:
            logger.info(f"Label '{label_name}' already exists (id={label['id']}).")
            return label["id"]

    # Label doesn't exist — create it
    label_body = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created = service.users().labels().create(userId="me", body=label_body).execute()
    logger.info(f"Created label '{label_name}' (id={created['id']}).")
    return created["id"]


def apply_label(service, message_id: str, label_id: str) -> None:
    """
    Apply a label to a Gmail message.

    Args:
        service: Gmail API service client.
        message_id: The message ID to label.
        label_id: The label ID to apply.
    """
    body = {"addLabelIds": [label_id]}
    service.users().messages().modify(userId="me", id=message_id, body=body).execute()
    logger.debug(f"Applied label {label_id} to message {message_id}.")


# ═══════════════════════════════════════════════════════════════
# 3B — Email Fetching
# ═══════════════════════════════════════════════════════════════

def get_owner_email(service) -> str:
    """Get the authenticated user's email address."""
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]
    logger.info(f"Owner email: {email}")
    return email


def fetch_candidate_emails(
    service,
    owner_email: str,
    max_results: int = 25,
    after_hours: int = None,
) -> list[str]:
    """
    Fetch candidate email message IDs from Inbox, excluding noise.

    Filters applied via Gmail search query:
      - Inbox only
      - Exclude Promotions & Updates categories
      - Exclude self-sent mail
      - Exclude already-processed and needs-human labels
      - Optionally restrict to recent N hours (first-run mode)

    Args:
        service: Gmail API service client.
        owner_email: The account owner's email (for self-sent exclusion).
        max_results: Maximum messages to return.
        after_hours: If set, only fetch emails from the last N hours.

    Returns:
        List of message ID strings.
    """
    query_parts = [
        "in:inbox",
        "-category:promotions",
        "-category:updates",
        f"-from:{owner_email}",
        "-label:Agent-Processed",
        "-label:Needs-Human",
    ]

    if after_hours is not None:
        query_parts.append(f"newer_than:{after_hours}h")

    query = " ".join(query_parts)
    logger.info(f"Gmail search query: {query}")

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    messages = results.get("messages", [])
    message_ids = [m["id"] for m in messages]
    logger.info(f"Found {len(message_ids)} candidate emails.")
    return message_ids


def get_message_detail(service, message_id: str) -> dict:
    """
    Fetch full message details and parse key fields.

    Returns:
        Dict with keys: message_id, thread_id, subject, from_email, body
    """
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    headers = msg.get("payload", {}).get("headers", [])
    subject = ""
    from_email = ""
    message_id_header = ""

    for h in headers:
        name = h["name"].lower()
        if name == "subject":
            subject = h["value"]
        elif name == "from":
            from_email = h["value"]
        elif name == "message-id":
            message_id_header = h["value"]

    # Extract body — prefer plain text, fall back to HTML
    body = _extract_body(msg.get("payload", {}))

    return {
        "message_id": msg["id"],
        "thread_id": msg["threadId"],
        "subject": subject,
        "from_email": from_email,
        "message_id_header": message_id_header,
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """
    Recursively extract the email body text from a Gmail payload.
    Prefers text/plain; falls back to text/html (stripped of tags).
    """
    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_base64(data)

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        return _decode_base64(data)

    # Multipart — recurse through parts
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            plain_text = _decode_base64(data)
        elif part_mime == "text/html":
            data = part.get("body", {}).get("data", "")
            html_text = _decode_base64(data)
        elif "multipart" in part_mime:
            # Nested multipart — recurse
            result = _extract_body(part)
            if result:
                plain_text = plain_text or result

    return plain_text if plain_text else html_text


def _decode_base64(data: str) -> str:
    """Decode Gmail's URL-safe base64-encoded body data."""
    if not data:
        return ""
    # Gmail uses URL-safe base64 without padding
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════
# 3C — Draft Management
# ═══════════════════════════════════════════════════════════════

def thread_has_draft(service, thread_id: str) -> bool:
    """
    Check if a thread already has a draft message.
    Secondary idempotency guard — prevents duplicate drafts if the agent
    crashes after creating a draft but before applying the label.

    Args:
        service: Gmail API service client.
        thread_id: The Gmail thread ID.

    Returns:
        True if the thread already contains a draft.
    """
    thread = service.users().threads().get(userId="me", id=thread_id, format="metadata").execute()
    for message in thread.get("messages", []):
        label_ids = message.get("labelIds", [])
        if "DRAFT" in label_ids:
            logger.debug(f"Thread {thread_id} already has a draft.")
            return True
    return False


def create_draft(
    service,
    thread_id: str,
    to_address: str,
    subject: str,
    body: str,
    in_reply_to: str = "",
) -> str:
    """
    Create a Gmail draft reply within a thread.

    NOTE: This function ONLY creates a draft. It NEVER sends email.
    The gmail.modify scope is used here but the send endpoint is
    intentionally never called anywhere in this codebase.

    Args:
        service: Gmail API service client.
        thread_id: Thread to attach the draft to.
        to_address: Recipient email.
        subject: Email subject (will be prefixed with "Re:" if needed).
        body: The draft reply body text.
        in_reply_to: Message-ID header of the original email (for threading).

    Returns:
        The created draft ID.
    """
    # Ensure subject has Re: prefix
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = MIMEText(body)
    message["to"] = to_address
    message["subject"] = subject

    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    draft_body = {
        "message": {
            "raw": raw,
            "threadId": thread_id,
        }
    }

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    draft_id = draft["id"]
    logger.info(f"Created draft {draft_id} in thread {thread_id}.")
    return draft_id
