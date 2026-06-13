# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Main Orchestrator
# Ties all modules together in the pipeline described in PRD §5
# ──────────────────────────────────────────────────────────────

import logging
import sys

from groq import Groq

from src.config import (
    GROQ_API_KEY,
    DRIVE_FOLDER_ID,
    KNOWLEDGE_CACHE_DIR,
    LABEL_AGENT_PROCESSED,
    LABEL_NEEDS_HUMAN,
    MAX_EMAILS_PER_RUN,
    FIRST_RUN_MAX_EMAILS,
    FIRST_RUN_LOOKBACK_HOURS,
)
from src.auth import get_credentials, build_gmail_service, build_drive_service
from src.gmail_client import (
    ensure_label_exists,
    apply_label,
    get_owner_email,
    fetch_candidate_emails,
    get_message_detail,
    thread_has_draft,
    create_draft,
)
from src.knowledge import load_knowledge_docs
from src.triage import triage_email
from src.drafter import draft_reply

logger = logging.getLogger(__name__)


def _is_first_run(gmail_service, label_id: str) -> bool:
    """
    Detect if this is the first run by checking if any emails
    carry the Agent-Processed label.
    """
    try:
        results = (
            gmail_service.users()
            .messages()
            .list(userId="me", labelIds=[label_id], maxResults=1)
            .execute()
        )
        has_processed = len(results.get("messages", [])) > 0
        return not has_processed
    except Exception:
        # If label doesn't exist yet or query fails, treat as first run
        return True


def run_agent(dry_run: bool = False) -> dict:
    """
    Main orchestration loop.

    Pipeline (from PRD §5):
      1. Authenticate to Gmail + Drive
      2. Ensure tracking labels exist
      3. Load knowledge documents (with caching)
      4. Determine first-run vs steady-state mode
      5. Fetch candidate emails
      6. For each email: triage → draft → label
      7. Log summary

    Args:
        dry_run: If True, skip draft creation and label application (testing mode).

    Returns:
        Summary dict with counts.
    """
    stats = {
        "total_candidates": 0,
        "triaged_out": 0,
        "needs_human": 0,
        "drafts_created": 0,
        "skipped_existing_draft": 0,
        "errors": 0,
    }

    # ── Step 1: Authenticate ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("Gmail Draft Agent — Starting run")
    logger.info("=" * 60)

    credentials = get_credentials()
    gmail_service = build_gmail_service(credentials)
    drive_service = build_drive_service(credentials)

    if not GROQ_API_KEY:
        raise ValueError("Missing GROQ_API_KEY environment variable.")
    groq_client = Groq(api_key=GROQ_API_KEY)

    logger.info("Authentication complete.")

    # ── Step 2: Ensure labels exist ───────────────────────────
    processed_label_id = ensure_label_exists(gmail_service, LABEL_AGENT_PROCESSED)
    needs_human_label_id = ensure_label_exists(gmail_service, LABEL_NEEDS_HUMAN)

    # ── Step 3: Load knowledge documents ──────────────────────
    knowledge_text = load_knowledge_docs(drive_service, DRIVE_FOLDER_ID, KNOWLEDGE_CACHE_DIR)

    if not knowledge_text.strip():
        logger.warning("No knowledge documents found! All queries will be flagged as Needs-Human.")

    # ── Step 4: Determine run mode ────────────────────────────
    first_run = _is_first_run(gmail_service, processed_label_id)

    if first_run:
        max_results = FIRST_RUN_MAX_EMAILS
        after_hours = FIRST_RUN_LOOKBACK_HOURS
        logger.info(f"FIRST RUN detected — processing max {max_results} emails from last {after_hours}h.")
    else:
        max_results = MAX_EMAILS_PER_RUN
        after_hours = None
        logger.info(f"Steady-state run — processing up to {max_results} emails.")

    # ── Step 5: Fetch candidate emails ────────────────────────
    owner_email = get_owner_email(gmail_service)
    message_ids = fetch_candidate_emails(
        gmail_service,
        owner_email=owner_email,
        max_results=max_results,
        after_hours=after_hours,
    )

    stats["total_candidates"] = len(message_ids)

    if not message_ids:
        logger.info("No candidate emails found. Nothing to do.")
        _log_summary(stats)
        return stats

    # ── Step 6: Process each email ────────────────────────────
    for i, msg_id in enumerate(message_ids, 1):
        logger.info(f"\n--- Email {i}/{len(message_ids)} (id={msg_id}) ---")

        try:
            detail = get_message_detail(gmail_service, msg_id)
            subject = detail["subject"]
            from_email = detail["from_email"]
            body = detail["body"]
            thread_id = detail["thread_id"]
            message_id_header = detail["message_id_header"]

            logger.info(f"From: {from_email} | Subject: {subject[:60]}")

            # ── Guard: skip if thread already has a draft ─────
            if thread_has_draft(gmail_service, thread_id):
                logger.info("Thread already has a draft. Skipping (idempotency guard).")
                stats["skipped_existing_draft"] += 1
                continue

            # ── Stage 1: Triage ───────────────────────────────
            is_query = triage_email(groq_client, subject, body)

            if not is_query:
                logger.info("Triage: NOT a customer query. Labeling as processed.")
                if not dry_run:
                    apply_label(gmail_service, msg_id, processed_label_id)
                stats["triaged_out"] += 1
                continue

            logger.info("Triage: IS a customer query. Proceeding to drafting.")

            # ── Stage 2: Drafting ─────────────────────────────
            answer_found, draft_body = draft_reply(groq_client, body, knowledge_text)

            if not answer_found:
                logger.info("Drafting: answer NOT found in docs. Labeling as Needs-Human.")
                if not dry_run:
                    apply_label(gmail_service, msg_id, needs_human_label_id)
                stats["needs_human"] += 1
                continue

            # ── Create draft & label (IDEMPOTENCY-CRITICAL ORDER) ──
            # Per PRD §7: create draft FIRST, then label IMMEDIATELY.
            # If crash occurs between these two steps, the
            # thread_has_draft() guard prevents duplicates on next run.
            logger.info("Drafting: answer FOUND. Creating Gmail draft...")

            if not dry_run:
                create_draft(
                    gmail_service,
                    thread_id=thread_id,
                    to_address=from_email,
                    subject=subject,
                    body=draft_body,
                    in_reply_to=message_id_header,
                )
                apply_label(gmail_service, msg_id, processed_label_id)

            stats["drafts_created"] += 1
            logger.info("Draft created and email labeled as Agent-Processed.")

        except Exception as e:
            logger.error(f"Error processing email {msg_id}: {e}", exc_info=True)
            stats["errors"] += 1
            continue  # Don't let one email failure stop the whole run

    # ── Step 7: Summary ───────────────────────────────────────
    _log_summary(stats)
    return stats


def _log_summary(stats: dict) -> None:
    """Log a summary of the agent run."""
    logger.info("\n" + "=" * 60)
    logger.info("RUN SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total candidates:       {stats['total_candidates']}")
    logger.info(f"  Triaged out (not query): {stats['triaged_out']}")
    logger.info(f"  Needs-Human (no answer): {stats['needs_human']}")
    logger.info(f"  Drafts created:          {stats['drafts_created']}")
    logger.info(f"  Skipped (existing draft):{stats['skipped_existing_draft']}")
    logger.info(f"  Errors:                  {stats['errors']}")
    logger.info("=" * 60)
