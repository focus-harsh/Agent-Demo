# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Knowledge Document Extraction & Caching
# ──────────────────────────────────────────────────────────────

import io
import json
import logging
import os

import PyPDF2
import docx

from src.drive_client import list_docs_in_folder, download_file

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract all text from a PDF file.

    Args:
        file_bytes: Raw PDF file bytes.

    Returns:
        Concatenated plain text from all pages.
    """
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)

    full_text = "\n\n".join(pages_text)
    logger.debug(f"Extracted {len(full_text)} chars from PDF ({len(reader.pages)} pages).")
    return full_text


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract all text from a Word (.docx) file.

    Args:
        file_bytes: Raw .docx file bytes.

    Returns:
        Concatenated plain text from all paragraphs.
    """
    document = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    full_text = "\n\n".join(paragraphs)
    logger.debug(f"Extracted {len(full_text)} chars from DOCX ({len(paragraphs)} paragraphs).")
    return full_text


def _extract_text(file_bytes: bytes, mime_type: str) -> str:
    """Route extraction to the correct parser based on MIME type."""
    if mime_type == "application/pdf":
        return extract_text_from_pdf(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(file_bytes)
    else:
        logger.warning(f"Unsupported MIME type: {mime_type}. Skipping.")
        return ""


def _load_manifest(cache_dir: str) -> dict:
    """Load the cache manifest (file_id → metadata mapping)."""
    manifest_path = os.path.join(cache_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(cache_dir: str, manifest: dict) -> None:
    """Save the cache manifest."""
    manifest_path = os.path.join(cache_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def load_knowledge_docs(drive_service, folder_id: str, cache_dir: str) -> str:
    """
    Load knowledge documents from Drive, using local cache when possible.

    Strategy:
      - List all docs in the Drive folder
      - For each doc, compare modifiedTime against cached metadata
      - If unchanged → load from cache (skip download + extraction)
      - If changed or new → download, extract text, save to cache
      - Return all texts concatenated (injected into drafting prompt)

    Args:
        drive_service: Drive API v3 service client.
        folder_id: Google Drive folder ID containing knowledge docs.
        cache_dir: Local directory for cached text files.

    Returns:
        Single concatenated string of all knowledge document texts.
    """
    os.makedirs(cache_dir, exist_ok=True)
    manifest = _load_manifest(cache_dir)
    all_texts = []
    cache_hits = 0
    cache_misses = 0

    docs = list_docs_in_folder(drive_service, folder_id)

    for doc in docs:
        file_id = doc["file_id"]
        name = doc["name"]
        modified_time = doc["modifiedTime"]
        mime_type = doc["mimeType"]
        cache_file = os.path.join(cache_dir, f"{file_id}.txt")

        # Check cache: is the file unchanged?
        cached = manifest.get(file_id, {})
        if (
            cached.get("modifiedTime") == modified_time
            and os.path.exists(cache_file)
        ):
            # Cache hit — load from disk
            with open(cache_file, "r", encoding="utf-8") as f:
                text = f.read()
            cache_hits += 1
            logger.debug(f"Cache hit for '{name}' ({file_id}).")
        else:
            # Cache miss — download and extract
            logger.info(f"Downloading '{name}' ({file_id}) — {'new' if file_id not in manifest else 'updated'}.")
            file_bytes = download_file(drive_service, file_id)
            text = _extract_text(file_bytes, mime_type)

            # Save to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(text)

            manifest[file_id] = {
                "name": name,
                "modifiedTime": modified_time,
                "mimeType": mime_type,
            }
            cache_misses += 1

        if text.strip():
            all_texts.append(f"--- Document: {name} ---\n{text}")

    _save_manifest(cache_dir, manifest)

    knowledge_text = "\n\n".join(all_texts)
    logger.info(
        f"Knowledge loaded: {len(docs)} docs, "
        f"{cache_hits} cached, {cache_misses} refreshed, "
        f"{len(knowledge_text)} total chars."
    )
    return knowledge_text
