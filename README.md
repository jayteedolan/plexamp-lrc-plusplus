# plexamp-lrc-plusplus

A self-hosted web tool that automatically finds and manages LRC lyric files for your Plex music library, fixing the common problem of missing, un-timed, or incorrectly matched lyrics in Plexamp.

Plex supports local `.lrc` sidecar files placed alongside audio files that override its built-in lyrics source. This tool automates fetching those files, lets you review and approve them album by album, and keeps your library up to date as new music is added.

## Features

- **Web UI** — browser-based management interface, runs on your Pi
- **Library scanner** — connects to Plex and discovers all tracks
- **Onboarding flow** — go album by album, preview proposed lyrics, approve/reject/edit
- **Background worker** — auto-fetches lyrics for new tracks, logs all activity
- **Plex refresh** — triggers Plex to re-scan after writing new `.lrc` files
- **Periodic scanning** — continuously checks for new tracks or missing lyrics

## Lyrics Sources

1. **LRCLIB** (primary) — free, no auth required, ~3M synced lyrics
2. **syncedlyrics** (fallback) — multi-provider: Musixmatch, NetEase, etc.
3. **Genius** (last resort) — plain text only, for when no synced lyrics exist

## Quick Start

### Requirements
- Docker + Docker Compose (recommended)
- A Plex server with a music library
- Your [Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)

### Setup

```bash
git clone https://github.com/jayteedolan/plexamp-lrc-plusplus
cd plexamp-lrc-plusplus
cp .env.example .env
# Edit .env — see Configuration below
docker compose up -d
```

Open `http://<your-pi-ip>:8000` in a browser.

## Configuration (`.env`)

```env
# Plex connection
PLEX_URL=http://192.168.1.x:32400   # your Plex server's LAN address
PLEX_TOKEN=                          # your Plex token
PLEX_LIBRARY_NAME=Music              # name of your music library section

# Music library path — must match the exact path Plex uses for file_path
# (this is how the tool knows where to write .lrc files)
MUSIC_DIR=/mnt/media/Music

# Scan settings
SCAN_INTERVAL_MINUTES=30
PORT=8000
```

### If Plex runs as a system service (most common)

Use your Pi's LAN IP for `PLEX_URL` — `localhost` won't work from inside the container.

### If Plex runs in Docker

Use Plex's service name (`http://plex:32400`) if both containers share a Docker network, or the Pi's LAN IP otherwise. Mount your music directory at the same container path Plex uses:

```yaml
# In docker-compose.yml, add to volumes:
- /host/path/to/music:/data/music   # same mapping as your Plex container
```

```env
MUSIC_DIR=/data/music
```

## Alternative: systemd (bare-metal, no Docker)

For Pi 3 or low-memory setups:

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill in your values
mkdir -p data
sudo cp plexamp-lrc.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now plexamp-lrc
```

## Architecture & Implementation Plan

See [PLAN.md](PLAN.md) for the full architecture, database schema, API endpoints, and phased implementation plan. That document is the authoritative reference for contributors and agents continuing this work.

## Project Status

Currently in initial planning phase. Implementation has not yet begun. See [PLAN.md](PLAN.md) for the roadmap.
