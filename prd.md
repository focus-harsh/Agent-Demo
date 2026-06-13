# PRD: Gmail Customer Query Draft Agent

**Owner:** Naveen S
**Status:** Draft v1
**Last updated:** June 12, 2026

---

## 1. Summary

An automated agent that monitors a consumer Gmail inbox, identifies genuine customer queries, and writes draft replies grounded strictly in a small set of knowledge documents. The agent never sends email. Humans review and send drafts inside Gmail as they already do. If the answer is not found in the knowledge documents, the agent writes no draft and flags the email for a human.

---

## 2. Goals and non-goals

| Goals | Non-goals |
|-------|-----------|
| Auto-detect real customer queries vs noise | Auto-send any email (explicitly forbidden) |
| Draft replies grounded only in knowledge docs | Build a new app, dashboard, or UI |
| Flag emails with no doc-based answer for humans | Maintain a separate database or state store |
| Keep cost low via cheap-then-better LLM tiering | Handle non-English email |
| Run unattended on a simple hourly schedule | Reply to follow-ups on already-handled threads (V1) |

---

## 3. Core safety rules

| Rule | Behavior |
|------|----------|
| No autonomous send | Agent only ever creates Gmail **drafts**. It has no send path in code. |
| No hallucination | If the answer is not present in the knowledge documents, the agent writes **no draft** and applies the `Needs-Human` label. |
| Grounding required | The drafting model must confirm the answer is found in supplied docs (`answer_found: true`) before any draft is created. Any ambiguity defaults to "not found". |
| Idempotency | An email is never drafted twice (label-based, see Section 7). |

---

## 4. Scope and assumptions

| Item | Decision |
|------|----------|
| Mailbox section | **Inbox only** |
| Account type | Consumer `@gmail.com` |
| Auth method | OAuth 2.0 with a stored long-lived refresh token (no service account) |
| Refresh token source | Generated via Google OAuth 2.0 Playground |
| Knowledge source | Under 10 PDF/Word files in one Google Drive folder; sole source of truth |
| Knowledge approach | Full document text injected into the drafting prompt (no vector search) |
| Email language | English only |
| Volume | ~10 to 20 emails/day |
| Triage basis | Decision uses the **email body content**, not just sender/headers |
| Pre-filter | Skip Gmail `CATEGORY_PROMOTIONS` and `CATEGORY_UPDATES` before any LLM call |
| Follow-ups | V1 drafts only on new mail content; threads already labeled are skipped |
| Self-sent mail | Emails sent by the account owner are ignored |
| Runtime | GitHub Actions scheduled job, hourly |
| LLM provider | Groq free tier for both triage and drafting |

---

## 5. High-level flow

```
GitHub Actions (hourly cron)
        |
        v
Authenticate to Gmail + Drive via OAuth refresh token
        |
        v
Load knowledge docs (from cache; refresh only if changed)
        |
        v
Fetch candidate emails from Inbox
  - exclude Promotions / Updates categories
  - exclude owner-sent mail
  - exclude anything labeled Agent-Processed or Needs-Human
  - exclude threads that already have a draft
        |
        v
For each candidate email:
   [1] CHEAP TRIAGE LLM  -> is this a real customer query? (yes/no)
            |  no  -> apply Agent-Processed, skip
            |  yes
            v
   [2] DRAFTING LLM (grounded in docs) -> {answer_found, draft}
            |  answer_found = false -> apply Needs-Human label, no draft
            |  answer_found = true
            v
        Create Gmail draft in the thread
            |
            v
        Apply Agent-Processed label  (immediately after draft)
```

---

## 6. Two-stage LLM design

| Stage | Purpose | Model (proposed) | Input | Output |
|-------|---------|------------------|-------|--------|
| 1. Triage | Decide if the email is a genuine customer query worth answering | `llama-3.1-8b-instant` (small, cheap, fast) | Email subject + body | `is_query: true/false` |
| 2. Drafting | Write a grounded reply or declare no answer | `llama-3.3-70b-versatile` (stronger reasoning) | Email body + full knowledge doc text | `answer_found: true/false`, `draft_body: string` |

**Model selection rationale:** triage is a simple binary classification, so the smallest fast model keeps cost and latency low. Drafting needs comprehension and grounding fidelity, so the larger model is justified on the much smaller subset that passes triage. Both are swappable via config.

**Structured output contract (Stage 2):**

```json
{
  "answer_found": true,
  "draft_body": "Hi ...,\n\n...\n\nBest regards"
}
```

The drafting prompt instructs the model to set `answer_found: false` whenever the response would require any information not explicitly present in the supplied documents. Default on ambiguity is `false`.

---

## 7. State tracking (no database)

Gmail labels are the single source of truth. No external state store.

| Label | Meaning | Applied when |
|-------|---------|--------------|
| `Agent-Processed` | Email has been handled (drafted, or triaged as non-query) | After a draft is created, or after triage rejects it |
| `Needs-Human` | Real query but no answer found in docs | When drafting returns `answer_found: false` |

**Skip logic on each run.** An email is skipped if any of these are true:
1. It carries `Agent-Processed`.
2. It carries `Needs-Human`.
3. Its thread already has a draft.
4. It belongs to `CATEGORY_PROMOTIONS` or `CATEGORY_UPDATES`.
5. It was sent by the account owner.

**Idempotency ordering (critical).** For each email: create draft → immediately apply `Agent-Processed` → only then move to the next email. If the run crashes after the draft but before the label, the secondary "thread already has a draft" guard prevents a duplicate on the next run.

---

## 8. Knowledge document handling

| Aspect | Decision |
|--------|----------|
| Location | One Google Drive folder |
| Formats | PDF and Word (.docx) |
| Strategy | Extract plain text from each doc, concatenate, inject into the drafting prompt |
| Retrieval | None. Volume is small enough to fit all text in context |
| Caching | Extracted text cached (committed to repo or stored as a build artifact). Re-extract only when a doc's Drive `modifiedTime` or checksum changes |
| Rationale | Docs change rarely; caching avoids re-downloading and re-parsing every hour |

---

## 9. First run vs steady state

| Run | Behavior |
|-----|----------|
| First run | Process at most the **latest 10 to 15 emails within the last 2 hours**. Do not backfill the whole inbox. |
| Steady state | Hourly cron picks up new mail since the previous run, gated by the skip logic in Section 7. |

---

## 10. Runtime and scheduling

| Aspect | Decision |
|--------|----------|
| Host | GitHub Actions, scheduled workflow |
| Frequency | Once per hour (`cron`) |
| Per-run cap | Max ~25 emails per run to avoid Groq rate limits on a backlog |
| Timing caveat | GitHub Actions cron is best-effort and may drift 5 to 30+ minutes or occasionally skip. SLA is "within roughly an hour", not exact |
| Rate-limit handling | Retry with exponential backoff on Groq 429s |

---

## 11. Authentication and secrets

| Item | Detail |
|------|--------|
| Gmail + Drive access | Single OAuth 2.0 client with Gmail and Drive scopes |
| Token type | Long-lived refresh token, generated via the Google OAuth 2.0 Playground |
| Storage | GitHub Actions Secrets (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GROQ_API_KEY`) |
| Critical prerequisite | The OAuth consent screen must be set to **Published / In production** (even if unverified). If left in "Testing" mode, the refresh token expires after 7 days and the agent silently stops |
| Scopes needed | `gmail.modify` (read, label, create drafts; not send), `drive.readonly` |

**Note on `gmail.modify`:** this scope allows creating drafts and applying labels but is used here without any send call. Send is never invoked in code.

---

## 12. Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Model hallucinates an answer not in docs | Medium | Structured `answer_found` gate; default to false on ambiguity; flag to `Needs-Human` |
| Refresh token expires (Testing mode) | High if missed | Publish OAuth consent screen as a setup step |
| Groq free-tier rate limits | Low at this volume | Per-run cap + backoff retry |
| Cron drift / skipped runs | Medium | Accept relaxed SLA; skip logic makes catch-up safe |
| Duplicate drafts on partial failure | Low | Strict draft-then-label ordering + draft-exists guard |
| Doc text too large for context | Low | Small doc set; monitor token count, fall back to retrieval only if it ever grows |
| Owner-sent or internal mail drafted | Low | Exclude owner-sent mail and use category pre-filter |

---

## 13. Success criteria

| Metric | Target |
|--------|--------|
| Autonomous sends | Zero, ever |
| Drafts grounded in docs | 100% of created drafts trace to doc content |
| Genuine queries with no draft | Correctly labeled `Needs-Human` |
| Duplicate drafts | Zero |
| Human action required | Only review-and-send, or handling `Needs-Human` items |

---

## 14. Open items for later versions

| Item | Note |
|------|------|
| Follow-up replies on labeled threads | Out of scope for V1; revisit if customers reply within threads often |
| Vector retrieval | Only if the knowledge base grows beyond what fits in context |
| Multi-language support | Out of scope; English only for now |
| Draft tone / signature standardization | Not specified yet; can be templated later |