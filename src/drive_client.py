# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Google Drive Client
# ──────────────────────────────────────────────────────────────
from __future__ import annotations

import io
import logging

from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

# Supported MIME types for knowledge documents
SUPPORTED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
]


def list_docs_in_folder(service, folder_id: str) -> list[dict]:
    """
    List PDF and Word documents in a Google Drive folder.

    Args:
        service: Drive API v3 service client.
        folder_id: The Google Drive folder ID.

    Returns:
        List of dicts with keys: file_id, name, mimeType, modifiedTime
    """
    mime_filter = " or ".join(f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES)
    query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

    results = (
        service.files()
        .list(q=query, fields="files(id, name, mimeType, modifiedTime)", pageSize=50)
        .execute()
    )

    files = results.get("files", [])
    logger.info(f"Found {len(files)} knowledge documents in Drive folder {folder_id}.")

    return [
        {
            "file_id": f["id"],
            "name": f["name"],
            "mimeType": f["mimeType"],
            "modifiedTime": f["modifiedTime"],
        }
        for f in files
    ]


def download_file(service, file_id: str) -> bytes:
    """
    Download a file's content from Google Drive.

    Args:
        service: Drive API v3 service client.
        file_id: The file ID to download.

    Returns:
        Raw bytes of the file.
    """
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_bytes = buffer.getvalue()
    logger.info(f"Downloaded file {file_id} ({len(file_bytes)} bytes).")
    return file_bytes
