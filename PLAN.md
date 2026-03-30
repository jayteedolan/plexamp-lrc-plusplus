# Plexamp LRC++ — Implementation Plan

## Context

Plexamp users frequently encounter lyrics that are missing, un-timed, mis-timed, or matched to the wrong song. Plex supports **local LRC sidecar files** placed alongside audio files (same filename, `.lrc` extension) that override its built-in lyrics source. This project is a self-hosted web tool to automate finding, reviewing, and deploying those LRC files for an entire Plex music library, running on a headless Raspberry Pi.

This repo also serves as **living documentation** — the plan, architecture decisions, and context are tracked here so anyone who clones the repo can understand and continue the work.

---

## Lyrics Source Strategy

| Source | Synced? | Auth? | Notes |
|--------|---------|-------|-------|
| **LRCLIB** (lrclib.net) | Yes (LRC) | None | Primary — free, ~3M songs, FOSS-friendly |
| **syncedlyrics** (PyPI) | Yes | Some providers need tokens | Fallback multi-provider: wraps LRCLIB, Musixmatch, NetEase |
| **Genius** | No (plain text) | Free API key | Last resort for un-synced lyrics when nothing else matches |

**Match confidence** is based on title + artist + duration (within ±3 seconds). LRCLIB has a `duration` field for exact matching. Reject if confidence is too low; flag for manual review.

---

## Architecture

Single Python process with three logical layers sharing one asyncio event loop:

```
┌─────────────────────────────────────────────────────┐
│  FastAPI (web server + API endpoints)                │
│  Jinja2 + HTMX (server-rendered UI, no JS framework)│
├─────────────────────────────────────────────────────┤
│  APScheduler (AsyncIOScheduler)                      │
│  • Startup scan job                                  │
│  • Periodic scan (default every 30 min)              │
│  • Auto-fetch job (processes pending tracks)         │
├─────────────────────────────────────────────────────┤
│  SQLite via SQLAlchemy (shared state)                │
└─────────────────────────────────────────────────────┘
```

---

## File Structure

```
plexamp-lrc-plusplus/
├── README.md                   ← setup/usage docs
├── PLAN.md                     ← this file — architecture and implementation plan
├── requirements.txt
├── .env.example
├── .gitignore                  ← includes data/, *.db, .env
├── Dockerfile                  ← python:3.11-slim image
├── docker-compose.yml          ← primary deployment method
├── plexamp-lrc.service         ← systemd unit file (alternative deployment)
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app factory, lifespan handler, scheduler start
│   ├── config.py               ← pydantic-settings, two-tier config (env + DB)
│   ├── database.py             ← SQLAlchemy engine, session factory, Base
│   ├── models.py               ← ORM models: Track, Album, ActivityLog, Config
│   ├── plex_client.py          ← plexapi wrapper (connect, enumerate tracks, refresh)
│   ├── lyrics_fetcher.py       ← LRCLIB → syncedlyrics → Genius fallback chain
│   ├── scanner.py              ← sync Plex library → DB, write LRC files to disk
│   ├── worker.py               ← APScheduler jobs wired to scanner/fetcher
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── dashboard.py        ← GET /  (stats, recent log)
│   │   ├── onboarding.py       ← GET/POST /onboarding  (album-by-album flow)
│   │   ├── library.py          ← GET /library  (browse all tracks/albums)
│   │   ├── logs.py             ← GET /logs  (activity log viewer)
│   │   └── settings.py         ← GET/POST /settings  (Plex config, intervals)
│   └── templates/
│       ├── base.html           ← nav, HTMX script tag, global styles link
│       ├── dashboard.html
│       ├── onboarding.html
│       ├── library.html
│       ├── logs.html
│       └── settings.html
├── static/
│   ├── style.css               ← minimal CSS (dark theme, mobile-friendly)
│   └── htmx.min.js             ← vendored HTMX (no CDN needed on Pi)
└── data/                       ← gitignored, created at runtime
    └── lyrics.db
```

---

## Database Schema

### `tracks` table
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| plex_track_id | String | Plex rating key (stable identifier) |
| plex_section_id | Integer | For targeted library section refresh |
| title | String | |
| artist | String | |
| album_artist | String | |
| album | String | |
| duration_ms | Integer | Used for lyrics match confidence |
| file_path | String | Absolute path to audio file |
| lrc_path | String | Computed: same dir, `.lrc` extension |
| lyrics_status | Enum | `pending` / `approved` / `rejected` / `missing` / `has_lrc` / `error` |
| lyrics_source | String | `lrclib` / `syncedlyrics` / `genius` / `manual` |
| lyrics_content | Text | LRC text stored in DB (avoid re-fetch on re-approve) |
| onboarding_status | Enum | `unreviewed` / `approved` / `rejected` / `skipped` |
| last_checked_at | DateTime | Last fetch attempt |
| lrc_written_at | DateTime | When .lrc was written to disk |
| plex_refreshed_at | DateTime | When Plex was triggered to refresh |
| created_at | DateTime | |
| updated_at | DateTime | Auto-update trigger |

### `albums` table
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| artist | String | Album artist |
| album | String | Album title |
| year | Integer | |
| onboarding_status | Enum | `not_started` / `in_progress` / `complete` / `skipped` |
| track_count | Integer | Cached |
| approved_count | Integer | Cached |
| created_at | DateTime | |

### `activity_log` table
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| timestamp | DateTime | |
| level | Enum | `info` / `warning` / `error` / `success` |
| category | Enum | `scan` / `fetch` / `write` / `plex_refresh` / `onboarding` / `system` |
| message | String | |
| track_id | Integer FK | Nullable, links to related track |

### `config` table
| Column | Type | Notes |
|--------|------|-------|
| key | String PK | |
| value | String | JSON-encoded |
| updated_at | DateTime | |

---

## Key API Endpoints

```
GET  /                          Dashboard (stats, recent log)
GET  /onboarding                Onboarding home (album list with progress)
GET  /onboarding/{album_id}     Album detail - show tracks with proposed lyrics
POST /onboarding/{album_id}/approve  Approve all or individual tracks
POST /onboarding/{album_id}/reject   Reject track(s)
POST /onboarding/{album_id}/skip     Skip album

GET  /library                   Browse all albums/tracks with lyrics status
GET  /library/track/{id}        Track detail (show LRC content, re-fetch button)
POST /library/track/{id}/refetch  Trigger re-fetch for a single track
POST /library/track/{id}/edit   Save manually edited LRC content

GET  /logs                      Activity log (paginated, filterable by level/category)
GET  /logs/stream               SSE endpoint for live log updates (HTMX sse extension)

GET  /settings                  Settings form
POST /settings                  Save settings (Plex URL, token, interval, etc.)
POST /settings/test-plex        Test Plex connection, return result inline (HTMX)

POST /api/scan                  Trigger manual library scan
POST /api/fetch-pending         Trigger immediate fetch run for all pending tracks
```

---

## Lyrics Fetcher Logic (`app/lyrics_fetcher.py`)

```
fetch_lyrics(track: Track) -> LyricsResult:
  1. Try LRCLIB:
     - GET /api/get?artist_name=...&track_name=...&album_name=...&duration=<seconds>
     - If synced lyrics found AND duration matches within ±3s → return (confidence: HIGH)
     - If synced lyrics found but duration mismatch → return (confidence: MEDIUM, flag for review)
     - If only plain lyrics found → store as fallback, continue

  2. Try syncedlyrics (fallback):
     - Queries LRCLIB again + Musixmatch + NetEase via unified interface
     - Return first synced result with acceptable confidence

  3. Try Genius (last resort, if prefer_unsynced=True in settings):
     - Fetches plain text lyrics
     - Wrap in basic LRC format without timestamps (Plex will show as static text)

  4. If nothing found → status = "missing", log it

LyricsResult:
  - content: str (LRC text)
  - is_synced: bool
  - source: str
  - confidence: "high" / "medium" / "low"
  - needs_review: bool (medium/low confidence → don't auto-approve)
```

**Auto-approval rule**: Only auto-approve if `confidence == "high"` (duration match within ±1s, exact title+artist match). Medium confidence → status stays `pending`, appears in onboarding for user review. Low confidence → status = `error`, logged.

---

## Scanner Logic (`app/scanner.py`)

```
sync_library(db, plex):
  - Enumerate all tracks via plexapi: plex.library.section(name).all()
  - For each track: upsert into `tracks` table by plex_track_id
  - Derive lrc_path from file_path (same dir, stem + ".lrc")
  - If lrc_path exists on disk → set status = "has_lrc" (don't overwrite)
  - Upsert albums table from distinct (album_artist, album) combos
  - Log: "Discovered N new tracks, M already have LRC files"

write_lrc(track: Track, content: str):
  - Write content to track.lrc_path (UTF-8)
  - Update track: lrc_written_at, lyrics_status = "approved"
  - Trigger plex_client.refresh_section(track.plex_section_id)
  - Update track: plex_refreshed_at
  - Log success
```

---

## Background Worker (`app/worker.py`)

APScheduler `AsyncIOScheduler` with these jobs:

| Job | Trigger | Action |
|-----|---------|--------|
| `startup_scan` | Once at startup | `sync_library()` |
| `periodic_scan` | Interval (default 30 min) | `sync_library()` to catch new tracks |
| `auto_fetch` | Interval (default 5 min) | Fetch lyrics for all `pending`/`missing` tracks |
| `retry_errors` | Interval (60 min) | Retry tracks in `error` state (up to 3 attempts) |

The `auto_fetch` job processes tracks in batches of 10 with a 500ms delay between requests (rate limiting). After each batch, it triggers a Plex section refresh for any tracks where LRC was newly written.

---

## Onboarding UX Flow

1. **Dashboard** shows "Onboarding: X of Y albums reviewed" progress bar with "Start / Continue Onboarding" button
2. **/onboarding** shows album grid sorted by: in-progress first, then not-started, then complete
3. **/onboarding/{album_id}** shows:
   - Album header (art, name, artist, year)
   - Track list — each row has: track number, title, duration, lyrics status badge
   - For each track with fetched lyrics: collapsible LRC preview
   - Action buttons per track: ✓ Approve / ✗ Reject / ✎ Edit
   - Album-level: "Approve All High-Confidence" / "Skip Album" buttons
   - Progress auto-saves on each action (no submit-all button needed)
4. On approve: calls `write_lrc()` immediately, triggers Plex refresh
5. On reject: sets `onboarding_status = rejected`, won't be re-offered
6. Lyrics editing: inline `<textarea>` with HTMX swap, validated LRC format on save

---

## Plex Client (`app/plex_client.py`)

Uses `plexapi`:
```python
from plexapi.server import PlexServer

connect(url, token) → PlexServer
get_tracks(section_name) → Iterator[Track dicts]
refresh_section(section_id)  # triggers Plex to re-scan that library section
test_connection() → bool, str  # used by settings page "Test Connection" button
```

The Plex token is obtained from your Plex account settings page and entered in the web UI. `plexapi` handles all HTTP communication with Plex.

---

## Deployment on Raspberry Pi

### Primary: Docker Compose

Docker Compose is the recommended deployment. It isolates the Python environment, handles restarts automatically, and requires no manual venv management. Works on Pi 4/5 (ARM64/ARM32v7 images available for `python:3.11-slim`).

**`Dockerfile`** (slim image):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`docker-compose.yml`**:
```yaml
services:
  plexamp-lrc:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data          # SQLite persistence
      - ${MUSIC_DIR}:${MUSIC_DIR} # Music library mounted at same absolute path Plex uses
```

The critical design: **the music library must be mounted at the same absolute path that Plex reports for each track's `file_path`**. When the scanner discovers `/mnt/media/Music/Artist/Album/01.mp3` from Plex's API, it writes `/mnt/media/Music/Artist/Album/01.lrc` directly — no path translation needed.

#### Scenario A: Plex as a system service (e.g., installed directly on the Pi)
Plex accesses music at e.g. `/mnt/media/Music` on the host directly.

```env
# .env
PLEX_URL=http://192.168.1.x:32400  # use Pi's LAN IP (not localhost — container can't resolve it)
PLEX_TOKEN=your_token_here
PLEX_LIBRARY_NAME=Music
MUSIC_DIR=/mnt/media/Music
```

The container reaches Plex via the Pi's LAN IP. The music dir is bind-mounted at the same path.

#### Scenario B: Plex running in Docker
Plex's music volume is mounted from a host path (e.g., `/mnt/media/Music` on host → `/data/music` in Plex container). Plex reports file paths as `/data/music/...`.

Mount that same host path at the same container path in our service:
```yaml
    volumes:
      - ./data:/app/data
      - /mnt/media/Music:/data/music   # same host→container mapping as Plex uses
```
```env
MUSIC_DIR=/data/music
PLEX_URL=http://plex:32400    # use Plex's service name if on same Docker network
```

If on the same Docker Compose project, add both services to a shared network. Otherwise use the Pi's LAN IP.

### Setup (both scenarios)
```bash
git clone https://github.com/jayteedolan/plexamp-lrc-plusplus
cd plexamp-lrc-plusplus
cp .env.example .env
# Edit .env: set PLEX_URL, PLEX_TOKEN, MUSIC_DIR
docker compose up -d
# Access UI at http://<pi-ip>:8000
```

### Alternative: systemd + venv (bare-metal)
For Pi 3 or low-memory situations where Docker overhead matters:

**`plexamp-lrc.service`**:
```ini
[Unit]
Description=Plexamp LRC++ Lyrics Manager
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/plexamp-lrc-plusplus
EnvironmentFile=/home/pi/plexamp-lrc-plusplus/.env
ExecStart=/home/pi/plexamp-lrc-plusplus/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env  # edit with your values
mkdir -p data
sudo cp plexamp-lrc.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now plexamp-lrc
```

---

## Implementation Phases

### Phase 1 — Project scaffold + config + DB
- `requirements.txt`, `.env.example`, `.gitignore`
- `app/config.py`, `app/database.py`, `app/models.py`
- `app/main.py` startup skeleton

### Phase 2 — Plex integration + library scanner
- `app/plex_client.py`
- `app/scanner.py` (sync_library, write_lrc)

### Phase 3 — Lyrics fetcher
- `app/lyrics_fetcher.py` with LRCLIB → syncedlyrics → Genius fallback chain
- Confidence scoring logic

### Phase 4 — Background worker
- `app/worker.py` (APScheduler jobs)
- Wire into `app/main.py` lifespan

### Phase 5 — Web UI
- `app/templates/base.html` + HTMX + CSS
- Dashboard, Library, Logs pages
- Settings page with Plex connection test

### Phase 6 — Onboarding flow
- `/onboarding` album grid
- `/onboarding/{album_id}` track review with approve/reject/edit
- HTMX live updates (status badges update without full page reload)

### Phase 7 — Polish + deployment
- `Dockerfile`, `docker-compose.yml`, `plexamp-lrc.service`
- `.env.example` with all required vars:
  ```
  PLEX_URL=http://192.168.1.x:32400
  PLEX_TOKEN=
  PLEX_LIBRARY_NAME=Music
  MUSIC_DIR=/path/to/your/music   # must match exact path Plex reports in file_path
  SCAN_INTERVAL_MINUTES=30
  PORT=8000
  ```
- README with full setup/usage docs for both Docker and bare-metal

---

## Risks and Gotchas

1. **PlexAmp local LRC display**: Some PlexAmp clients prefer LyricFind over local files. The tool writes `.lrc` sidecar files per Plex's official spec — if a client still ignores them, that's a PlexAmp client bug. The web player version handles local lyrics correctly.

2. **File system write permissions**: In Docker, the container runs as root by default — fine for writing LRC files. For systemd, the service user (`pi`) must have write access to the music dir (check group membership if the drive is owned by `plex`). `MUSIC_DIR` must match exactly what Plex reports for file paths — even a trailing slash difference will break writes.

3. **LRCLIB rate limiting**: No documented rate limit, but the worker uses 500ms delays between requests to be polite.

4. **Plex token security**: Never commit `.env` to git (`.gitignore` covers it). The settings page shows the token masked.

5. **Duration matching**: LRC files for the wrong song version (live vs. studio, remaster) will have wrong timing. The ±3s tolerance and confidence scoring catch most cases; medium-confidence tracks go to onboarding for human review.

6. **Large libraries**: A library with 50,000+ tracks will take time for the initial scan. The worker processes in batches and logs progress. The web UI remains responsive during scanning (async jobs).

---

## Verification

After implementation, verify end-to-end:
1. Configure Plex settings → click "Test Connection" → should show library track count
2. Trigger manual scan → check activity log shows discovered tracks
3. Navigate to `/onboarding` → see albums listed
4. Open one album → lyrics should be pre-fetched and shown → approve one track
5. Check that `.lrc` file was created on disk alongside the audio file
6. Check that Plex re-scanned (check `plex_refreshed_at` in DB)
7. Open Plexamp web player → confirm lyrics appear for that track
8. Wait for periodic scan to run (or trigger manually) → log updates in `/logs`
