# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Configuration
# ──────────────────────────────────────────────────────────────

import os

# ─── Authentication ──────────────────────────────────────────
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ─── Google Drive ────────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "15XgE7EeSK_iyMvk-J0aPTYtznl-oWSy_")

# ─── OAuth Scopes ────────────────────────────────────────────
# gmail.modify: read, label, create drafts (NOT send)
# drive.readonly: read knowledge docs from Drive
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# ─── LLM Models (Groq) ──────────────────────────────────────
TRIAGE_MODEL = "llama-3.1-8b-instant"           # cheap, fast — binary classification
DRAFTING_MODEL = "llama-3.3-70b-versatile"       # stronger reasoning for grounded replies

# ─── Email Processing Limits ────────────────────────────────
MAX_EMAILS_PER_RUN = 25          # steady-state cap to avoid Groq rate limits
FIRST_RUN_MAX_EMAILS = 15        # first run: only recent mail
FIRST_RUN_LOOKBACK_HOURS = 2     # first run: only last N hours

# ─── Gmail Labels (state tracking) ──────────────────────────
LABEL_AGENT_PROCESSED = "Agent-Processed"
LABEL_NEEDS_HUMAN = "Needs-Human"

# ─── Knowledge Cache ────────────────────────────────────────
KNOWLEDGE_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_cache")

# ─── Retry Settings ─────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2   # seconds; exponential backoff: 2, 4, 8 …

# ─── Polling Settings ───────────────────────────────────────
CHECK_INTERVAL_SECONDS = 5
