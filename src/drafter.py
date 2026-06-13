# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Drafting Stage (Stage 2)
# Grounded reply generation from knowledge documents
# ──────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
import os
import time

from src.config import DRAFTING_MODEL, MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

# Load prompt template once
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "drafting_prompt.txt")

# Approximate token-to-char ratio for warning when context gets large
_CHARS_PER_TOKEN_APPROX = 4
_CONTEXT_WARNING_TOKENS = 100_000  # warn if knowledge text is this many tokens


def _load_drafting_prompt() -> str:
    """Load the drafting prompt template from disk."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def draft_reply(groq_client, email_body: str, knowledge_text: str) -> tuple[bool, str]:
    """
    Generate a grounded draft reply using the knowledge documents.

    Uses a stronger model (llama-3.3-70b-versatile) for comprehension and
    grounding fidelity. The model must confirm the answer exists in the
    supplied docs — if not, it returns answer_found=false and no draft.

    DEFAULT ON AMBIGUITY IS FALSE — this is a core safety rule.

    Args:
        groq_client: Initialized Groq client.
        email_body: The customer's email body text.
        knowledge_text: Concatenated text from all knowledge documents.

    Returns:
        Tuple of (answer_found: bool, draft_body: str).
        If answer_found is False, draft_body will be empty.
    """
    # Token count warning
    approx_tokens = len(knowledge_text) // _CHARS_PER_TOKEN_APPROX
    if approx_tokens > _CONTEXT_WARNING_TOKENS:
        logger.warning(
            f"Knowledge text is ~{approx_tokens} tokens — approaching context limit. "
            f"Consider switching to vector retrieval."
        )

    prompt_template = _load_drafting_prompt()
    prompt = (
        prompt_template
        .replace("{{knowledge_text}}", knowledge_text)
        .replace("{{email_body}}", email_body)
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = groq_client.chat.completions.create(
                model=DRAFTING_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1024,
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            answer_found = result.get("answer_found", False)
            draft_body = result.get("draft_body", "")

            # Safety: if answer_found is somehow true but draft is empty, treat as not found
            if answer_found and not draft_body.strip():
                logger.warning("answer_found=True but draft_body is empty. Overriding to False.")
                answer_found = False

            logger.info(
                f"Drafting result: answer_found={answer_found}, "
                f"draft_length={len(draft_body)} chars"
            )
            return (answer_found, draft_body)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Groq rate limit hit (attempt {attempt}/{MAX_RETRIES}). "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Drafting LLM error: {e}")
                raise

    # All retries exhausted — default to NOT FOUND (safe: don't hallucinate)
    logger.warning("Drafting retries exhausted. Defaulting to answer_found=False.")
    return (False, "")
