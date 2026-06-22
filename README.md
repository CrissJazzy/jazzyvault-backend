# JazzyVault — Backend

Secure AI-powered document vault. Convert. Store. Secure. Smarter.

This is the Python FastAPI backend for JazzyVault, deployed on **Render**.

> Frontend repo: `jazzyvault-frontend` (Next.js 15, deployed on Netlify)

---

## Tech Stack

- FastAPI
- Supabase (PostgreSQL, Auth, Storage) via `supabase-py`
- Google Gemini API (primary AI provider) — provider-agnostic AI service layer
- `slowapi` for rate limiting
- JWT verification of Supabase-issued tokens

---

## Build Status — Phased Delivery

- [x] **Phase 1** — Project Foundation
- [x] **Phase 2** — Authentication System
- [x] **Phase 3** — File Upload & Storage
- [x] **Phase 4** — Document Conversion Engine
- [x] **Phase 5** — Conversion History & Analytics
- [x] **Phase 6** — AI Document Intelligence
- [x] **Phase 7** — Dashboard Enhancement
- [x] **Phase 8** — Security & Optimization (this README)
- [ ] Phase 9 — Deployment

---

## Phase 8 — What Was Built

This phase started with an audit, not an assumption — every existing route, schema, and config setting was checked against what was actually there before deciding what to add.

### Rate limiting (was the biggest gap)

Audited every route across all 6 route files. **Every GET endpoint, plus `logout`, `track_download`, and `delete_file`, had zero rate limiting** — only the original Phase 2/4/6 POST endpoints did. All now limited:

| Tier | Limit | Used for |
|---|---|---|
| Reads (file/conversion/AI lists, single-item GETs, `/auth/me`) | 60/minute | Cheap, frequent, low individual risk |
| Search (`/dashboard/search`) | 30/minute | Three DB queries per call |
| Deletes, conversion history | 30/minute | Slightly more sensitive than plain reads |
| Logout | 20/minute | Low risk but no reason to leave unlimited |
| Conversion/AI history | 30–60/minute | Read-only but can be expensive |

**Also fixed: rate limiting was silently broken behind Render's proxy.** `slowapi`'s `get_remote_address` reads `X-Forwarded-For`, but without telling Uvicorn to trust the upstream proxy, every request would appear to come from Render's internal proxy IP — meaning the limiter would effectively rate-limit *all users combined* as if they were one client, or not work at all depending on header presence. Fixed by adding `--proxy-headers --forwarded-allow-ips='*'` to the Dockerfile's Uvicorn command (verified against community-documented `slowapi`/Uvicorn behavior — see Dockerfile comments for the full explanation and why `forwarded-allow-ips='*'` is safe specifically in Render's single-hop setup).

### Input validation

- **`file_id`/`conversion_id`/`request_id`** — previously plain unconstrained `str` in both request bodies (`ConvertRequest`, `AIActionRequest`) and path parameters (`GET /files/{file_id}`, etc.). Now validated against a UUID pattern (`app/core/validators.py`), so malformed IDs get a clean `422` instead of a wasted DB round-trip.
- **`target_format`** in `ConvertRequest` — previously any string; now validated against the actual set of supported target formats.
- **Filename sanitization** — `upload.filename` is attacker-controlled and was previously used unsanitized in both the Supabase Storage path and the DB `file_name` column. New `sanitize_filename()` (`app/utils/file_validation.py`) strips path separators, control characters, and filesystem-unsafe characters, normalizes Unicode, and bounds length — while still preserving the readable name and extension. This doesn't enable cross-user access (Storage RLS already scopes every path to the owner — see migration 002), but prevents broken uploads from special characters and cleans up what gets shown in `Content-Disposition` on download. **Actually tested** (not just syntax-checked) against 11 cases including path traversal attempts, null bytes, and Unicode filenames — all passed; see test output in this PR's history if you want to rerun it yourself.

### Security headers

The API previously sent zero security response headers — middleware. New `SecurityHeadersMiddleware` (`app/core/security_headers.py`) adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Strict-Transport-Security` to every response. Also narrowed CORS `allow_methods`/`allow_headers` from `["*"]` to exactly what this API uses (confirmed no route uses PUT/PATCH before narrowing).

### Performance: fixed a real N+1

`GET /files` signed a download URL **per file, sequentially** — a vault with 50 files meant 50 separate Supabase Storage API calls just to render the list. Now uses `create_signed_urls()` (the batch variant, confirmed against official Supabase Python docs) to sign an entire page of results in one call. Also added a `limit` param (default 200) to `GET /files`, matching the pattern already used by conversion/AI history — previously unbounded.

---## ⚠️ Phase 6 — Critical Fix: Deprecated Gemini SDK

Phase 1 specified `google-generativeai` for the AI layer. **That package is deprecated and reached end-of-life on August 31, 2025** — Google replaced it with a new SDK, `google-genai`, with a meaningfully different API. This was caught during Phase 6 implementation by checking current documentation before writing code, not assumed correct from training data.

**What changed:**
- `requirements.txt`: `google-generativeai==0.8.3` → `google-genai==2.3.0`
- API shape: the old SDK used `genai.configure(api_key=...)` + `genai.GenerativeModel(...)`. The new SDK uses `client = genai.Client(api_key=...)` + `client.aio.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(...))`.
- Default model: Phase 1's `gemini-1.5-flash` guess updated to `gemini-2.5-flash` (current as of this implementation).

If you're following along from Phase 1's original plan and already installed `google-generativeai`, uninstall it and run `pip install -r requirements.txt` again to pick up the new package.

---

## Phase 7 — What Was Built

**New endpoint:** `GET /dashboard/search?q=...` — global search across `files`, `conversions`, and `ai_requests` in one call, merged and sorted by recency. Backs the frontend's `⌘K` command palette.

**Note on architecture:** this is the only new backend surface for Phase 7 — the bulk of this phase was frontend work (global search UI, mobile navigation, AI request history view, loading skeletons), since the search/filter/sort functionality the original Phase 7 spec called for was already built incrementally in Phases 3 (files), 5 (conversions), and 6 (AI, backend only — the frontend list view was the gap closed this phase).

**Audit finding:** most of the existing UI's responsive behavior (table column hiding, filter-bar wrapping, grid breakpoints) turned out to already be solid from earlier phases. The one genuine gap was a completely missing mobile navigation — the sidebar was `hidden md:flex` with no small-screen alternative at all, meaning phone users had no way to navigate between sections except typing URLs directly. That's fixed with a new bottom tab bar (see frontend README).

---

## Phase 6 — What Was Built

**New database table:** `ai_requests` (migration 006) — tracks every AI Document Intelligence call: file, request type, input params (e.g. target language), response text, status, which provider handled it. RLS-scoped to the owner, same pattern as `conversions`.

**Provider-agnostic AI layer** (`app/services/ai_providers/`), exactly matching the Phase 1 architecture requirement — switching `AI_PROVIDER=gemini` → `openai` or `groq` requires zero code changes anywhere else in the application:
- `base.py` — abstract `AIProvider` interface (`generate()`)
- `gemini.py` — the active/default provider, using the current `google-genai` SDK
- `openai_provider.py`, `groq_provider.py` — fully implemented secondary providers (not just stubs), ready to activate by changing one environment variable. Note: Groq's API uses `max_completion_tokens` instead of OpenAI's `max_tokens` — a real difference between the two otherwise-similar SDKs, handled correctly rather than copy-pasted.
- `factory.py` — the single place that branches on `AI_PROVIDER`
- `text_extraction.py` — pulls plain text from DOCX/PDF/TXT for the AI to process (images, PPTX, XLSX aren't text-extractable with this MVP's tooling)
- `prompts.py` — prompt templates for each of the five request types

**New endpoints:** `POST /ai/summarize`, `/ai/insights`, `/ai/simplify`, `/ai/translate`, `/ai/analyze`, plus `GET /ai/history` and `GET /ai/{request_id}`. All authenticated, rate-limited (15/minute), and scoped to the requesting user.

**Activity logging:** every AI request logs an `ai_request` activity entry — this type was already future-proofed into the `activity_logs` CHECK constraint back in Phase 5, so no schema change was needed here.

---

## Phase 5 — What Was Built

**New database table:** `activity_logs` (migration 004) — a unified feed of uploads, deletes, downloads, conversion starts/completions/failures, and a future-ready `ai_request` type for Phase 6.

**Existing tables, no schema changes:** `conversions` (Phase 4) already had every field the Phase 5 spec asked for, so it wasn't touched. One correctness fix was needed though — `conversions` has two foreign keys to `files` (input and output), and the new history endpoint needs to embed the input file's name/size via a PostgREST join, which requires the foreign keys to be unambiguously named. Migration 005 renames them explicitly; it's additive and safe to run even if you already applied migration 003.

**New endpoints:**
- `GET /dashboard/stats` — total files, total/successful/failed conversions, storage used/limit
- `GET /activity/recent` — paginated activity feed, most recent first
- `POST /files/{file_id}/track-download` — lets the frontend record a download event (the backend never otherwise sees a download, since files are fetched directly from Storage via signed URL)

**Extended endpoint (not replaced):** `GET /convert/history` (Phase 4) gained new optional query params — `search`, `type` (e.g. `docx-pdf`), `date_from`, `date_to`, `sort_order` — while keeping its original `status` and `limit` params working exactly as before. It now also returns `file_name` and `file_size` per conversion (via the new `ConversionHistoryEntry`/`ConversionHistoryResponse` schemas), since the History page needs those and the original `ConversionResponse` schema — still used unchanged by `POST /convert` and `GET /convert/{id}` — deliberately doesn't carry them.

**Activity logging wired into existing services:** `file_service.py` (upload, delete) and `conversion_service.py` (started, completed, failed) now call into a new `ActivityService.log()` at the relevant points. These are additive calls only — no existing logic in those files was changed, and logging failures are caught and swallowed (a logging hiccup should never break an upload or conversion).

---

## ⚠️ Phase 4 — Architecture Change: Docker Deployment Required

Back in Phase 1, this README flagged that `docx2pdf` wouldn't work on Render's native Python runtime. Here's the actual fix that's now implemented:

**What changed:**
- DOCX↔PDF conversion now shells out to **LibreOffice headless** (`soffice --headless --convert-to ...`) via `app/services/conversion/libreoffice.py`, instead of any Python DOCX-to-PDF library.
- PDF↔image conversion uses `pdf2image`, which wraps the `poppler-utils` system binaries (`pdftoppm`/`pdftocairo`).
- **Neither LibreOffice nor poppler-utils can be installed on Render's native Python runtime** — that runtime's build step doesn't give you `apt-get`/root access. The only reliable way to get these system dependencies onto Render (confirmed against Render's own docs) is **Docker deployment**, where Render builds and runs a `Dockerfile` you control.
- `render.yaml` has been updated: `runtime: python` → `runtime: docker`, pointing at the new `Dockerfile` in this repo. This works on Render's **free tier** — Docker web services are fully supported there, not a paid-only feature.

**What this means for you:**
- Local development is unaffected if you have LibreOffice and poppler installed on your machine (see below). If you don't want to install them locally, you can instead run the backend via `docker build` / `docker run` using the same Dockerfile Render uses — see "Local Setup" below for both options.
- On Render, nothing changes about how you deploy except: Render will now build from the Dockerfile instead of running `pip install`. The Blueprint (`render.yaml`) handles this automatically.

**Real resource caveat (please read before relying on this in production):** Render's **free tier** gives you 0.1 CPU / 512MB RAM. LibreOffice headless is memory-hungry — it commonly uses 200–400MB+ per conversion — and large or complex DOCX files may be slow or occasionally fail/timeout on the free tier under that constraint. This is a genuine limitation of running LibreOffice on a free-tier container, not a bug in this code. If conversions are unreliable in production, the standard fix is upgrading to a paid Render instance with more RAM.

---

## Phase 2–6 — Required Database Migrations

Run these in order, in **Supabase Dashboard → SQL Editor**:

### 1. `supabase/migrations/001_profiles.sql`

Creates:
- `profiles` table (1:1 with `auth.users`)
- Row Level Security policies (users can only read/update their own profile)
- A trigger (`handle_new_user`) that automatically inserts a profile row whenever someone registers — runs at the database level, so it fires regardless of whether registration happens through this API, the frontend's direct Supabase calls, or the Supabase dashboard.

You'll also need `SUPABASE_JWT_SECRET` in your `.env` — find it in **Supabase Dashboard → Project Settings → API → JWT Settings → JWT Secret**.

### 2. `supabase/migrations/002_files.sql`

Creates:
- `files` table with RLS (users only see their own files)
- The `jazzyvault-files` Storage bucket — **private**, created via SQL (`insert into storage.buckets`)
- Storage object policies scoped by `{user_id}/...` path prefix
- Triggers that keep `profiles.storage_used_bytes` in sync automatically on file insert/delete

**Verify the bucket exists:** Supabase Dashboard → Storage — you should see `jazzyvault-files` listed. If the SQL insert into `storage.buckets` didn't take effect in your project version, create it manually: **New bucket → name `jazzyvault-files` → Public bucket: OFF**, then re-run just the policy statements from the migration.

### 3. `supabase/migrations/003_conversions.sql`

Creates the `conversions` table (tracks every conversion job: input file, output file, formats, status, error message) with RLS so users only see their own conversion history.

### 4. `supabase/migrations/004_activity_logs.sql`

Creates the `activity_logs` table — a unified feed of uploads, deletes, downloads, and conversion events, with RLS so users only see their own activity. No automatic retention/pruning is configured; see the migration's comments if this table needs archiving in a high-traffic deployment.

### 5. `supabase/migrations/005_rename_conversion_fkeys.sql`

Explicitly names the two foreign keys from `conversions` to `files` (`input_file_id` and `output_file_id`). This is required because `GET /convert/history` now embeds the input file's name/size via a PostgREST join, and PostgREST can't disambiguate which of the two foreign keys to use without an explicit name. **Safe to run even if migration 003 was already applied** — it only renames existing constraints, no data is touched.

### 6. `supabase/migrations/006_ai_requests.sql`

Creates the `ai_requests` table, tracking every AI Document Intelligence call (summarize/insights/simplify/translate/analyze) with RLS so users only see their own AI request history.

---

## Phase 2 — Auth Endpoints

| Method | Path | Auth required | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Register a new user (also creates session if email confirmation is disabled) |
| POST | `/auth/login` | No | Log in with email + password |
| POST | `/auth/logout` | No (token optional) | Invalidate the current session |
| POST | `/auth/password-reset` | No | Send a password reset email (always returns success, regardless of whether the email exists) |
| GET | `/auth/me` | Yes (Bearer token) | Returns the current user's profile |

**Note on architecture:** the frontend's auth forms (login/register/reset) call Supabase directly via the JS SDK rather than through this API — this is the standard, recommended pattern (`@supabase/ssr` is built for exactly this, and it keeps password handling entirely within Supabase's infrastructure). These backend endpoints exist for: (1) any future non-browser client (mobile app, CLI, server-to-server), and (2) `/auth/me`, which the frontend dashboard calls to fetch the full profile record using its Supabase-issued JWT.

---

## Phase 3 — File Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/files/upload` | Multipart upload, accepts multiple files under the `files` field. Returns per-file success/failure. |
| GET | `/files` | List the current user's files. Query params: `search`, `file_type`, `sort_by` (`created_at`\|`file_name`\|`file_size`), `sort_order` (`asc`\|`desc`) |
| GET | `/files/{file_id}` | Get a single file (returns a fresh signed URL) |
| DELETE | `/files/{file_id}` | Delete a file from both Storage and the database |

**Important architectural note:** the `jazzyvault-files` bucket is **private**. Every file response includes a signed URL that expires after 1 hour (`SIGNED_URL_EXPIRY_SECONDS` in `app/services/file_service.py`) — these are generated fresh on every `GET`, never stored permanently, since a stored signed URL would eventually go stale. If your frontend keeps a file list open for over an hour without refetching, download/preview links may need a refresh.

---

## Phase 4 — Conversion Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/convert` | Start a conversion. Body: `{ "file_id": "...", "target_format": "pdf" }`. Runs synchronously and returns once complete (or failed). |
| GET | `/convert/history` | List the current user's conversions. Originally Phase 4, extended in Phase 5 — see below. |
| GET | `/convert/{conversion_id}` | Get a single conversion record |

**Supported conversions** (per project spec):

| From | To |
|---|---|
| DOCX | PDF |
| PDF | DOCX, JPG, PNG |
| JPG / PNG | PDF |

A converted output file is automatically saved as a new row in the `files` table — it appears in the Vault like any uploaded file, with its own signed URL. Multi-page PDF→image conversions save one file per page.

**Note on PDF→DOCX fidelity:** LibreOffice's PDF import filter does a reasonable but imperfect job reconstructing editable DOCX structure from a PDF, especially for complex layouts. This is a known limitation of the underlying tool, not something this code can fully work around.

---

## Phase 5 — Conversion History, Dashboard & Activity Endpoints

### `GET /convert/history` (extended from Phase 4)

All original Phase 4 query params still work exactly as before. New optional ones added in Phase 5:

| Param | Description |
|---|---|
| `status` | *(Phase 4)* Filter by `pending`\|`processing`\|`completed`\|`failed` |
| `limit` | *(Phase 4)* Max results, default 50, max 200 |
| `search` | *(new)* Search by the source file's name |
| `type` | *(new)* Filter by `"input_format-output_format"`, e.g. `docx-pdf` |
| `date_from` / `date_to` | *(new)* ISO date/datetime bounds on `created_at` |
| `sort_order` | *(new)* `desc` (default, newest first) or `asc` (oldest first) |

The response shape also changed for this endpoint specifically: it now returns `ConversionHistoryEntry` objects (includes `file_name` and `file_size`, joined from `files` via the source file) instead of the plain `ConversionResponse` used elsewhere. `POST /convert` and `GET /convert/{id}` are unchanged and still return `ConversionResponse`.

### `GET /dashboard/stats`

Returns: `total_files`, `total_conversions`, `successful_conversions`, `failed_conversions`, `storage_used_bytes`, `storage_limit_bytes`.

### `GET /activity/recent`

Returns the current user's most recent activity log entries (uploads, deletes, downloads, conversion events), newest first. Query param: `limit` (default 20, max 100).

### `POST /files/{file_id}/track-download`

Records a `file_download` activity entry. The frontend calls this alongside triggering an actual download (which happens client-side via signed URL and is otherwise invisible to the backend). Best-effort — never blocks the download itself.

All four endpoints require authentication and only ever return/affect data scoped to `current_user.id`, consistent with every other endpoint in this API.

---

## Phase 6 — AI Document Intelligence Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/ai/summarize` | Summarize a document |
| POST | `/ai/insights` | Extract key insights as a bulleted list |
| POST | `/ai/simplify` | Rewrite in plain, accessible language |
| POST | `/ai/translate` | Translate to a target language |
| POST | `/ai/analyze` | Smart analysis: purpose, themes, tone, gaps |
| GET | `/ai/history` | List the current user's AI requests, most recent first. Query param: `limit` (default 50, max 200) |
| GET | `/ai/{request_id}` | Get a single AI request |

**Request body** for the five action endpoints: `{ "file_id": "...", "target_language": "..." }` — `target_language` is only used (and required) by `/ai/translate`.

**Supported file types:** DOCX, PDF, TXT only — these are the formats this MVP can extract plain text from. Sending a JPG/PNG/PPTX/XLSX file returns a `400` with a clear message rather than failing silently.

**Rate limit:** 15 requests/minute per IP, since AI calls are the most expensive operation in this API (both in latency and, depending on the provider, cost).

**Switching providers:** change `AI_PROVIDER` in your environment to `gemini` (default), `openai`, or `groq`, and set the corresponding API key. No code changes anywhere — see `app/services/ai_providers/factory.py`.

---

## Phase 7 — Global Search Endpoint

### `GET /dashboard/search?q=...`

Searches across all three of the user's content types in one call:
- **Files** — matched by filename
- **Conversions** — matched by the *source file's* filename (joined via the same `conversions_input_file_fkey` constraint named in migration 005)
- **AI requests** — matched by the *source file's* filename, or by request type (e.g. searching "translate" surfaces all translation requests)

Results are capped at 8 per type and merged into one list sorted by recency. Each result includes a `link` field telling the frontend which page to navigate to (`/files`, `/conversions`, or `/ai-tools`) — there's no individual result detail page, results land you on the relevant list view.

---

## Local Setup

You have two options locally: run directly with `uvicorn` (requires LibreOffice + poppler installed on your machine), or run via Docker (uses the exact same environment Render will use).

### Option A — Direct (uvicorn)

#### 1. Install system dependencies (required for Phase 4 conversion features)

```bash
# macOS
brew install libreoffice poppler

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y libreoffice poppler-utils

# Windows: install LibreOffice from libreoffice.org and poppler via
# conda install -c conda-forge poppler, then ensure both are on PATH.
```

If you skip this, everything except DOCX/PDF/image conversion will still work fine — auth, file upload, and the vault don't need these.

#### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

#### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 4. Configure environment variables

```bash
cp .env.example .env
```

Fill in your Supabase project credentials (Project Settings → API) and your Gemini API key (from [Google AI Studio](https://aistudio.google.com/apikey)).

#### 5. Run the dev server

```bash
uvicorn app.main:app --reload
```

### Option B — Docker (matches Render's production environment exactly)

```bash
cp .env.example .env   # fill in your credentials first
docker build -t jazzyvault-backend .
docker run --rm -p 8000:8000 --env-file .env jazzyvault-backend
```

This builds the same image Render deploys, including LibreOffice and poppler — useful for confirming conversion behavior will actually work in production before you push.

### Verify it's running

Visit [http://localhost:8000/health](http://localhost:8000/health) — you should see `{"status": "healthy", ...}`.

To confirm Phases 2–8, open [http://localhost:8000/docs](http://localhost:8000/docs) and try:
1. `POST /auth/register` with a test email/password — should return a `201` with user + session (or a `202` if email confirmation is required).
2. Copy the `access_token` from the response, click **Authorize** in the Swagger UI, paste it in as `Bearer <token>`.
3. `GET /auth/me` — should return the profile that was auto-created by the database trigger.
4. `POST /files/upload` — attach a small **TXT or DOCX** file under the `files` field (you'll reuse this for the AI steps below, so a text-heavy file is more useful here than an image). Should return `201` with the uploaded file's metadata and a signed URL.
5. `GET /files` — should list the file you just uploaded.
6. `POST /convert` with `{"file_id": "<id from step 4>", "target_format": "pdf"}` (or another supported pair) — should return a `201` with `status: "completed"` and an `output_file_id`. If LibreOffice/poppler aren't installed (Option A without step 1), this will fail with a clear error message rather than crashing silently.
7. `GET /convert/history` — should show the conversion you just ran, now including `file_name` and `file_size`. Try `?search=`, `?type=pdf-jpg`, `?sort_order=asc` to confirm the new Phase 5 filters work.
8. `GET /dashboard/stats` — should reflect the upload and conversion you just did (`total_files: 1`, `total_conversions: 1`, `successful_conversions: 1`).
9. `GET /activity/recent` — should show entries for the upload (`file_upload`) and conversion (`conversion_started` then `conversion_completed`), newest first.
10. `POST /files/{file_id from step 4}/track-download` — should return `200` with a confirmation message, and a new `file_download` entry should appear at the top of `GET /activity/recent`.
11. `POST /ai/summarize` with `{"file_id": "<id from step 4>"}` — requires a real `GEMINI_API_KEY` in your `.env` (get one free at [Google AI Studio](https://aistudio.google.com/apikey)). Should return `201` with `status: "completed"` and a `response` field containing the summary.
12. `GET /ai/history` — should show the summarize request you just ran.
13. Try `POST /ai/translate` with `{"file_id": "...", "target_language": "French"}` to confirm the language-specific path works.
14. `GET /dashboard/search?q=<part of your test file's name>` — should return at least the file you uploaded in step 4, and likely the conversion and AI request you ran against it too, all merged into one `results` list.
15. **Phase 8 — rate limiting:** call `GET /files` more than 60 times within a minute (a quick shell loop works) — you should get a `429 Too Many Requests` once you exceed the limit, not silently succeed forever.
16. **Phase 8 — input validation:** try `POST /convert` with `{"file_id": "not-a-uuid", "target_format": "pdf"}` — should return a clean `422` with a validation error, not a 500 or a confusing DB error.
17. **Phase 8 — filename sanitization:** upload a file with a deliberately awkward name (e.g. `my report (final) v2!!.pdf` or one with accented characters) — should upload successfully and the punctuation/diacritics should be preserved or cleanly replaced, not cause an error.
18. **Phase 8 — security headers:** check the raw response headers on any request (e.g. `curl -I http://localhost:8000/health`) — should include `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
19. **Phase 8 — N+1 fix:** upload 5+ files, then `GET /files` and check response time — should feel roughly constant regardless of file count, not noticeably slower with more files (this is hard to verify precisely without load-testing tools, but a gross regression would be obvious).

---

## Folder Structure

```
app/
  api/routes/
    auth.py              → register, login, logout, password-reset, me (all rate-limited Phase 8)
    files.py               → upload, list (+limit param Phase 8), get, delete, track-download (Phase 5) (all rate-limited Phase 8)
    conversion.py            → convert, history (extended Phase 5), get (all rate-limited Phase 8)
    dashboard.py               → stats (Phase 5), global search (Phase 7) (rate-limited Phase 8)
    activity.py                  → recent activity feed (Phase 5) (rate-limited Phase 8)
    ai.py                          → summarize, insights, simplify, translate, analyze, history, get (Phase 6) (all rate-limited Phase 8)
  core/
    config.py              → environment-driven settings (Pydantic)
    security.py              → Supabase JWT verification dependency
    limiter.py                 → shared rate limiter instance
    validators.py                → shared UUID_PATTERN for request validation (Phase 8)
    security_headers.py            → SecurityHeadersMiddleware (Phase 8)
  models/                        → internal data models
  schemas/
    auth.py                       → Pydantic request/response schemas for auth
    files.py                        → Pydantic request/response schemas for files
    conversion.py                     → ConversionResponse + ConversionHistoryEntry/Response (Phase 5), UUID/format validation (Phase 8)
    dashboard.py                        → DashboardStats, ActivityLogEntry, ActivityFeedResponse (Phase 5), GlobalSearchResponse (Phase 7)
    ai.py                                 → AIActionRequest, AIRequestResponse, AIRequestListResponse (Phase 6), UUID validation (Phase 8)
  services/
    auth_service.py                  → Supabase Auth orchestration logic
    file_service.py                    → Storage upload/list/delete + signed URL minting (+ activity logging Phase 5, batch signing + filename sanitization Phase 8)
    conversion_service.py                → orchestrates a conversion job end-to-end (+ activity logging, Phase 5)
    activity_service.py                    → writes activity_logs rows (Phase 5)
    dashboard_service.py                     → aggregates stats + recent activity (Phase 5), global search (Phase 7)
    ai_service.py                              → orchestrates an AI request end-to-end (Phase 6)
    conversion/
      libreoffice.py                           → soffice subprocess wrapper (DOCX<->PDF)
      image_converter.py                         → Pillow/pdf2image wrapper (image<->PDF)
    ai_providers/                                  → provider-agnostic AI layer (Phase 6)
      base.py                                         → abstract AIProvider interface
      gemini.py                                         → active/default provider (google-genai SDK)
      openai_provider.py                                  → secondary provider, fully implemented
      groq_provider.py                                      → secondary provider, fully implemented
      factory.py                                              → the one place that branches on AI_PROVIDER
      prompts.py                                                → prompt templates per request type
      text_extraction.py                                          → DOCX/PDF/TXT -> plain text
  db/
    supabase_client.py                               → admin (service-role) and anon Supabase clients
  utils/
    file_validation.py                                 → allowed extensions/MIME types, sanitize_filename (Phase 8)
  main.py                                                → FastAPI app entrypoint, CORS (tightened Phase 8), rate limiting, security headers (Phase 8), routers
supabase/
  migrations/
    001_profiles.sql                                      → profiles table, RLS, auto-create trigger
    002_files.sql                                           → files table, storage bucket + policies, usage triggers
    003_conversions.sql                                       → conversions table, RLS
    004_activity_logs.sql                                       → activity_logs table, RLS (Phase 5)
    005_rename_conversion_fkeys.sql                               → names conversions->files FKs for PostgREST embedding (Phase 5)
    006_ai_requests.sql                                             → ai_requests table, RLS (Phase 6)
Dockerfile                                                  → installs LibreOffice + poppler (+ --proxy-headers Phase 8), used for local + Render
.dockerignore
tests/                                                         → pytest suite
```

---

## AI Provider Strategy

The AI layer is provider-agnostic by design. Switch providers with a single environment variable:

```bash
AI_PROVIDER=gemini   # default — generous free tier, ideal for MVP
AI_PROVIDER=openai   # future
AI_PROVIDER=groq     # future
```

No application code changes are required to switch — implemented via a factory pattern in `app/services/ai_providers/factory.py`. As of Phase 6, `gemini` is fully wired and active by default; `openai` and `groq` are also fully implemented (not stubs) and ready to use by setting `AI_PROVIDER` and the corresponding API key — they just aren't the default, per the project's cost-optimization requirement.

---

## ✅ Resolved: Gemini SDK Deprecation (caught during Phase 6)

Phase 1's plan specified `google-generativeai`, which turned out to be deprecated (EOL Aug 31, 2025) by the time Phase 6 was implemented. See "⚠️ Phase 6 — Critical Fix: Deprecated Gemini SDK" above for the full explanation — this section exists so the Phase 1 "future" framing isn't left stale now that it's done.

## ⚠️ Verify Before Deploying: Gemini SDK (google-genai)

Same caveat as the Supabase note below, for the same reason (no network access in this sandbox to actually install and run it): `app/services/ai_providers/gemini.py` was written against `google-genai`'s documented API (verified via official docs and PyPI as of this implementation — `client.aio.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(...))`, response text via `.text`), but not boot-tested against a live install.

**Before deploying:** run a `POST /ai/summarize` request locally with a real `GEMINI_API_KEY`. If it fails with an import error or attribute error rather than a clean `AIProviderError` message, check the installed `google-genai` version's exact API against [the PyPI page](https://pypi.org/project/google-genai/) — the SDK has changed rapidly (releases roughly weekly) since its initial release.

## ⚠️ Verify Before Deploying: Supabase SDK Method Names

This sandbox has no network access, so `app/services/auth_service.py` could not be boot-tested against a live `supabase-py` install. The method names used (`sign_up`, `sign_in_with_password`, `sign_out`, `reset_password_for_email`) were cross-checked against the official Supabase Python docs, but the exact attribute names on the returned `Session` object (`expires_in`, `expires_at`, `token_type`) were not independently verifiable offline — `_session_to_schema()` uses `getattr()` fallbacks defensively for this reason.

**Before deploying:** run `register` and `login` locally once, and if `expires_in`/`expires_at` come back as `None`/default in the response, print `vars(result.session)` to see the real attribute names on your installed `supabase-py` version and adjust `_session_to_schema()` accordingly.

## ✅ Resolved: Document Conversion Platform Compatibility (was flagged in Phase 1)

This was originally flagged as an open risk back in Phase 1: `docx2pdf` (now removed from `requirements.txt`) relies on Microsoft Word or LibreOffice being installed **locally** via COM/AppleScript and doesn't work on Linux. It's now resolved — see "⚠️ Phase 4 — Architecture Change: Docker Deployment Required" above for the full explanation. Short version: conversion now uses LibreOffice headless + poppler-utils, installed at the OS level via the `Dockerfile`, with Render deploying via Docker instead of its native Python runtime.

---

## Deployment — Render

This repo includes `render.yaml` (Render Blueprint) for one-click setup. As of Phase 4, this deploys via **Docker** (`runtime: docker`), not Render's native Python buildpack — required for the LibreOffice/poppler system dependencies that document conversion needs.

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** → connect the repo. Render will read `render.yaml` automatically and detect the `Dockerfile`.
3. Fill in the environment variables marked `sync: false` in the Render dashboard (Supabase keys, Gemini API key, etc.) — these are secrets and aren't stored in the blueprint.
4. Render builds the Docker image (this takes longer than a plain `pip install` — LibreOffice is a large package — expect the first deploy to take several minutes) and starts the container, which runs:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
5. Health checks hit `/health`.

**Free tier notes:**
- Render's free web services spin down after inactivity and take ~30–60 seconds to wake on the next request. Worth surfacing in the frontend UX (e.g. a loading state) once deployed.
- Free tier is 0.1 CPU / 512MB RAM. LibreOffice conversions are memory-intensive — see the Phase 4 architecture note above for what to expect and the upgrade path if conversions are unreliable under load.

---

## Security Notes

- `SUPABASE_SERVICE_ROLE_KEY` bypasses Row Level Security — it is backend-only and must **never** be sent to the frontend or committed to version control.
- All protected routes will depend on `get_current_user` (`app/core/security.py`), which verifies the Supabase-issued JWT against `SUPABASE_JWT_SECRET`.
- Rate limiting is configured via `slowapi`, default `60/minute`, applied per-route as routes are added.
