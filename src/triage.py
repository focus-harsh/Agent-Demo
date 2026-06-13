# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Triage Stage (Stage 1)
# Cheap/fast LLM binary classification: is this a real customer query?
# ──────────────────────────────────────────────────────────────

import json
import logging
import os
import time

from src.config import TRIAGE_MODEL, MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

# Load prompt template once
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "triage_prompt.txt")


def _load_triage_prompt() -> str:
    """Load the triage prompt template from disk."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def triage_email(groq_client, subject: str, body: str) -> bool:
    """
    Determine if an email is a genuine customer query worth drafting a reply for.

    Uses a cheap, fast model (llama-3.1-8b-instant) for binary classification.
    This is Stage 1 of the two-stage LLM pipeline — only emails that pass
    triage proceed to the more expensive drafting stage.

    Args:
        groq_client: Initialized Groq client.
        subject: Email subject line.
        body: Email body text.

    Returns:
        True if the email is a genuine customer query, False otherwise.
    """
    prompt_template = _load_triage_prompt()
    prompt = prompt_template.replace("{{subject}}", subject).replace("{{body}}", body)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = groq_client.chat.completions.create(
                model=TRIAGE_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=50,
            )

            content = response.choices[0].message.content
            result = json.loads(content)
            is_query = result.get("is_query", False)

            logger.info(
                f"Triage result: is_query={is_query} "
                f"(subject='{subject[:50]}...')"
            )
            return bool(is_query)

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
                logger.error(f"Triage LLM error: {e}")
                raise

    # All retries exhausted — default to treating as a query (safe side: don't ignore real queries)
    logger.warning("Triage retries exhausted. Defaulting to is_query=True (safe fallback).")
    return True
