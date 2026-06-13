# Gmail Customer Query Draft Agent — Task Breakdown

> Atomic tasks phased by dependency. Each phase must be complete before the next begins.

---

## Phase 0 — Prerequisites & Manual Setup (No Code) ✅

- [x] Create a Google Cloud project
- [x] Enable the **Gmail API** in the GCP project
- [x] Enable the **Google Drive API** in the GCP project
- [x] Create OAuth 2.0 Client ID credentials (Desktop app type)
- [x] Note down `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
- [x] Set OAuth consent screen to **Published / In production** (critical — Testing mode tokens expire in 7 days)
- [x] Add required scopes: `gmail.modify`, `drive.readonly`
- [x] Generate a long-lived refresh token via [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground)
- [x] Obtain a **Groq API key** from Groq's free tier
- [ ] Create a GitHub repository for the agent *(deferred to Phase 8)*
- [ ] Add GitHub Actions secrets *(deferred to Phase 8)*:
  - [ ] `GOOGLE_CLIENT_ID`
  - [ ] `GOOGLE_CLIENT_SECRET`
  - [ ] `GOOGLE_REFRESH_TOKEN`
  - [ ] `GROQ_API_KEY`
- [x] Create (or identify) the Google Drive folder containing knowledge docs (PDF/Word)
- [x] Note the Drive folder ID → `15XgE7EeSK_iyMvk-J0aPTYtznl-oWSy_`
- [x] Store the Drive folder ID as a GitHub secret or config value (`DRIVE_FOLDER_ID`)

---

## Phase 1 — Project Skeleton & Configuration ✅

- [x] Initialize the project directory structure
- [x] Create `requirements.txt` with dependencies
- [x] Create `src/config.py`:
  - [x] Define env var names
  - [x] Define configurable constants: `TRIAGE_MODEL`, `DRAFTING_MODEL`
  - [x] Define `MAX_EMAILS_PER_RUN = 25`
  - [x] Define `FIRST_RUN_MAX_EMAILS = 15`
  - [x] Define `FIRST_RUN_LOOKBACK_HOURS = 2`
  - [x] Define label names: `LABEL_AGENT_PROCESSED`, `LABEL_NEEDS_HUMAN`
  - [x] Define owner email address config (dynamic via `get_owner_email`)
- [x] Create `.env.example` with placeholder values for all secrets
- [x] Create `.env` with real credentials
- [x] Create `.gitignore`

---

## Phase 2 — OAuth Authentication Module

- [x] Create `src/auth.py`
- [x] Implement `get_credentials()`:
  - [x] Read `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` from env vars
  - [x] Construct a `google.oauth2.credentials.Credentials` object using the refresh token
  - [x] Set token URI to `https://oauth2.googleapis.com/token`
  - [x] Set scopes to `['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/drive.readonly']`
  - [x] Return the credentials object
- [x] Implement `build_gmail_service(credentials)` → returns Gmail API service client
- [x] Implement `build_drive_service(credentials)` → returns Drive API service client
- [ ] Write unit test: verify credentials construction with mock env vars
- [ ] Write unit test: verify service clients are built without error

---

## Phase 3 — Gmail Client Module ✅

### 3A — Label Management
- [x] Create `src/gmail_client.py`
- [x] Implement `ensure_label_exists(service, label_name)`
- [x] Implement `apply_label(service, message_id, label_id)`
- [ ] Write unit tests for label management

### 3B — Email Fetching
- [x] Implement `get_owner_email(service)`
- [x] Implement `fetch_candidate_emails(service, owner_email, max_results, after_hours)`
  - [x] Gmail query: `in:inbox -category:promotions -category:updates -from:{owner} -label:Agent-Processed -label:Needs-Human`
- [x] Implement `get_message_detail(service, message_id)` with multipart body parsing
- [ ] Write unit tests for email fetching

### 3C — Draft Management
- [x] Implement `thread_has_draft(service, thread_id)` — idempotency guard
- [x] Implement `create_draft(service, thread_id, to_address, subject, body, in_reply_to)` with MIME threading
- [ ] Write unit tests for draft management

---

## Phase 4 — Drive Client & Knowledge Document Handling ✅

### 4A — Drive Client
- [x] Create `src/drive_client.py`
- [x] Implement `list_docs_in_folder(service, folder_id)` with MIME type filter
- [x] Implement `download_file(service, file_id)` via `MediaIoBaseDownload`

### 4B — Knowledge Extraction & Caching
- [x] Create `src/knowledge.py`
- [x] Implement `extract_text_from_pdf(file_bytes)` using PyPDF2
- [x] Implement `extract_text_from_docx(file_bytes)` using python-docx
- [x] Implement `load_knowledge_docs(drive_service, folder_id, cache_dir)` with manifest-based caching
- [x] Implement cache storage: `knowledge_cache/{file_id}.txt` + `manifest.json`
- [ ] Write unit tests for knowledge extraction & caching

---

## Phase 5 — LLM Integration (Groq) ✅

### 5A — Triage Stage
- [x] Create `src/triage.py`
- [x] Create `prompts/triage_prompt.txt` with binary classification prompt
- [x] Implement `triage_email(groq_client, subject, body)` with JSON mode
- [x] Implement retry with exponential backoff on HTTP 429
- [ ] Write unit tests for triage

### 5B — Drafting Stage
- [x] Create `src/drafter.py`
- [x] Create `prompts/drafting_prompt.txt` with grounding rules + `{{knowledge_text}}` / `{{email_body}}` placeholders
- [x] Implement `draft_reply(groq_client, email_body, knowledge_text)` with JSON mode
- [x] Implement retry with exponential backoff on HTTP 429
- [x] Add token count check: log warning if knowledge text approaches context limit
- [ ] Write unit tests for drafting

---

## Phase 6 — Agent Orchestrator ✅

- [x] Create `src/agent.py`
- [x] Implement `run_agent(dry_run)` — full pipeline:
  - [x] Step 1: Authenticate (Gmail + Drive + Groq)
  - [x] Step 2: Ensure labels exist (`Agent-Processed`, `Needs-Human`)
  - [x] Step 3: Load knowledge docs with caching
  - [x] Step 4: First-run detection + mode selection
  - [x] Step 5: Fetch candidate emails
  - [x] Step 6: Process loop (triage → draft → label with idempotency ordering)
  - [x] Step 7: Summary logging
- [x] Per-email error isolation (one failure doesn't stop the run)
- [ ] Write integration test with mocked APIs

---

## Phase 7 — Entry Point & CLI ✅

- [x] Create `src/__main__.py`:
  - [x] `--dry-run` flag for testing without side effects
  - [x] `--verbose` flag for debug logging
  - [x] Auto-loads `.env` for local dev via python-dotenv
  - [x] Proper exit codes (0 success, 1 failure)
- [ ] Verify local execution works end-to-end with real credentials

---

## Phase 8 — GitHub Actions Workflow ✅

- [x] Create `.github/workflows/agent.yml`:
  - [x] Hourly cron: `0 * * * *`
  - [x] Manual `workflow_dispatch` with dry-run option
  - [x] Python 3.11 on ubuntu-latest
  - [x] All secrets injected as env vars
- [ ] Test workflow with `workflow_dispatch` manual trigger
- [ ] Verify logs show expected output in GitHub Actions
- [ ] Verify no emails are sent (only drafts created)



---

## Phase 9 — End-to-End Verification

- [ ] **Test: Promotional email** → Confirm it's never fetched / no LLM call made
- [ ] **Test: Self-sent email** → Confirm it's excluded from candidates
- [ ] **Test: Non-query email** (e.g., auto-reply, newsletter) → Confirm triage rejects it, `Agent-Processed` label applied, no draft
- [ ] **Test: Customer query with answer in docs** → Confirm draft is created in correct thread, `Agent-Processed` label applied
- [ ] **Test: Customer query without answer in docs** → Confirm no draft created, `Needs-Human` label applied
- [ ] **Test: Duplicate run** → Re-run agent immediately; confirm no duplicate drafts (idempotency)
- [ ] **Test: Thread with existing draft** → Confirm email is skipped
- [ ] **Test: First run** → Confirm only last 2 hours / max 15 emails processed
- [ ] **Test: Per-run cap** → Send >25 emails; confirm only 25 processed
- [ ] **Test: Groq rate limit** → Simulate 429; confirm retry with backoff works
- [ ] **Verify: Zero sends** → Audit Gmail Sent folder; confirm nothing was sent by the agent
- [ ] **Verify: Draft content grounding** — Spot-check 5 drafts manually; confirm each answer traces to knowledge doc text

---

## Phase 10 — Documentation & Hardening

- [ ] Write `README.md`:
  - [ ] Project overview and purpose
  - [ ] Architecture diagram (text-based flowchart)
  - [ ] Setup instructions (GCP project, OAuth, Drive folder)
  - [ ] How to generate the refresh token
  - [ ] How to configure GitHub secrets
  - [ ] How to trigger a manual run
  - [ ] How to add/update knowledge documents
  - [ ] Troubleshooting: token expiry, rate limits, missing labels
- [ ] Add inline code comments on critical sections:
  - [ ] Idempotency ordering (draft → label)
  - [ ] Why `gmail.modify` is used but send is never called
  - [ ] Default-to-false grounding logic
- [ ] Add logging throughout (structured, with timestamps):
  - [ ] Auth success/failure
  - [ ] Number of knowledge docs loaded (cached vs refreshed)
  - [ ] Each email: ID, subject snippet, triage result, draft result
  - [ ] Run summary stats
- [ ] Review all error handling paths — ensure no unhandled exceptions crash silently
