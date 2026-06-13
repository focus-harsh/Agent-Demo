# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — OAuth Authentication
# ──────────────────────────────────────────────────────────────

import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REFRESH_TOKEN,
    SCOPES,
    TOKEN_URI,
)

logger = logging.getLogger(__name__)


def get_credentials() -> Credentials:
    """
    Build OAuth2 credentials from environment variables (refresh token flow).

    Returns:
        google.oauth2.credentials.Credentials ready for API calls.

    Raises:
        ValueError: if any required credential env var is missing.
    """
    missing = []
    if not GOOGLE_CLIENT_ID:
        missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not GOOGLE_REFRESH_TOKEN:
        missing.append("GOOGLE_REFRESH_TOKEN")

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    creds = Credentials(
        token=None,                       # will be refreshed automatically
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    logger.info("OAuth credentials constructed successfully.")
    return creds


def build_gmail_service(credentials: Credentials):
    """Build and return the Gmail API v1 service client."""
    service = build("gmail", "v1", credentials=credentials)
    logger.info("Gmail service client built.")
    return service


def build_drive_service(credentials: Credentials):
    """Build and return the Google Drive API v3 service client."""
    service = build("drive", "v3", credentials=credentials)
    logger.info("Drive service client built.")
    return service
