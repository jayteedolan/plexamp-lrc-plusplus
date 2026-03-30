from __future__ import annotations

from typing import Iterator

from plexapi.exceptions import Unauthorized, NotFound
from plexapi.server import PlexServer


def connect(url: str, token: str) -> PlexServer:
    return PlexServer(url, token, timeout=10)


def test_connection(url: str, token: str) -> tuple[bool, str]:
    """Test Plex connection. Returns (ok, message)."""
    try:
        server = connect(url, token)
        music_sections = [
            s for s in server.library.sections() if s.type == "artist"
        ]
        total_tracks = sum(s.totalSize for s in music_sections)
        section_names = ", ".join(s.title for s in music_sections)
        if music_sections:
            msg = f"Connected — found {total_tracks:,} tracks across {len(music_sections)} library section(s): {section_names}"
        else:
            msg = "Connected, but no music libraries found. Check your library name."
        return True, msg
    except Unauthorized:
        return False, "Invalid token — check your Plex token and try again."
    except (ConnectionError, TimeoutError, OSError) as e:
        return False, f"Could not reach Plex at {url} — {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"Unexpected error: {e}"


def get_music_libraries(url: str, token: str) -> list[dict]:
    """Return all music library sections as dicts with id and title."""
    try:
        server = connect(url, token)
        return [
            {"key": s.key, "title": s.title}
            for s in server.library.sections()
            if s.type == "artist"
        ]
    except Exception:  # noqa: BLE001
        return []


def get_tracks(url: str, token: str, library_name: str) -> Iterator[dict]:
    """Yield track dicts for every track in the named music library."""
    server = connect(url, token)
    try:
        section = server.library.section(library_name)
    except NotFound:
        raise ValueError(f"Library '{library_name}' not found on this Plex server.")

    for track in section.searchTracks():
        media = track.media[0] if track.media else None
        part = media.parts[0] if (media and media.parts) else None
        file_path = part.file if part else ""

        yield {
            "plex_track_id": str(track.ratingKey),
            "plex_section_id": int(section.key),
            "title": track.title or "",
            "artist": track.grandparentTitle or "",
            "album_artist": track.grandparentTitle or "",
            "album": track.parentTitle or "",
            "duration_ms": track.duration or None,
            "file_path": file_path,
            "year": getattr(track, "year", None),
        }


def refresh_section(url: str, token: str, section_id: int) -> None:
    """Trigger a Plex library section refresh."""
    server = connect(url, token)
    section = server.library.sectionByID(section_id)
    section.update()
