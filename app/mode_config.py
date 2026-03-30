from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session


class OperatingMode(str, Enum):
    NORMAL = "normal"
    DEBUG = "debug"
    DANGEROUS = "dangerous"


class ConfidenceThreshold(str, Enum):
    HIGH = "high"       # high confidence only
    MEDIUM = "medium"   # medium or higher
    LOW = "low"         # everything (any confidence)


@dataclass
class ModeConfig:
    mode: OperatingMode = OperatingMode.NORMAL
    dangerous_threshold: ConfidenceThreshold = field(default=ConfidenceThreshold.HIGH)

    @property
    def is_debug(self) -> bool:
        return self.mode == OperatingMode.DEBUG

    @property
    def capture_trace(self) -> bool:
        """True when raw API responses should be captured for display."""
        return self.mode == OperatingMode.DEBUG

    def should_auto_approve(self, confidence: str) -> bool:
        """Return True if a track with this confidence should be written without user review."""
        if self.mode == OperatingMode.NORMAL:
            return confidence == "high"
        if self.mode == OperatingMode.DEBUG:
            return False  # debug mode always queues for manual review
        if self.mode == OperatingMode.DANGEROUS:
            if self.dangerous_threshold == ConfidenceThreshold.HIGH:
                return confidence == "high"
            if self.dangerous_threshold == ConfidenceThreshold.MEDIUM:
                return confidence in ("high", "medium")
            return confidence is not None  # LOW = approve anything found
        return False


# ---------------------------------------------------------------------------
# Lyric resolution settings — separate from operating mode
# ---------------------------------------------------------------------------

# Possible values for lyric_source_preference config key
PREFER_PLEX = "prefer_plex"
PREFER_LRCPLUSPLUS = "prefer_lrcplusplus"

# Possible outcomes of resolve_lyrics()
USE_OURS = "use_ours"          # write a .lrc file from LRC++ fetch result
USE_PLEX = "use_plex"          # leave .lrc unwritten — Plex serves its own lyrics
FLAG_MISSING = "flag_missing"  # nothing good found; mark track for attention


def get_config_value(db: Session, key: str, default: str = "") -> str:
    from app.models import Config
    row = db.get(Config, key)
    return row.value if row else default


def set_config_value(db: Session, key: str, value: str) -> None:
    from app.models import Config
    row = db.get(Config, key)
    if row:
        row.value = value
    else:
        db.add(Config(key=key, value=value))
    db.commit()


def get_mode_config(db: Session) -> ModeConfig:
    """Load the current operating mode from the DB config table."""
    mode_str = get_config_value(db, "operating_mode", OperatingMode.NORMAL)
    threshold_str = get_config_value(db, "dangerous_threshold", ConfidenceThreshold.HIGH)
    try:
        mode = OperatingMode(mode_str)
    except ValueError:
        mode = OperatingMode.NORMAL
    try:
        threshold = ConfidenceThreshold(threshold_str)
    except ValueError:
        threshold = ConfidenceThreshold.HIGH
    return ModeConfig(mode=mode, dangerous_threshold=threshold)


def get_lyric_settings(db: Session) -> dict:
    """Load all lyric source preference settings from the DB config table.

    Keys returned:
        has_plex_pass             bool  — if False, ignore Plex lyrics entirely
        lyric_source_preference   str   — "prefer_plex" | "prefer_lrcplusplus"
        timed_override            bool  — (prefer_plex sub-toggle) if True, our
                                          timed .lrc beats Plex's plain text
        accept_plex_timed_if_plain bool — (prefer_lrcplusplus sub-toggle) if True,
                                          use Plex's timed when we only found plain
    """
    return {
        "has_plex_pass": get_config_value(db, "has_plex_pass", "true") == "true",
        "lyric_source_preference": get_config_value(db, "lyric_source_preference", PREFER_PLEX),
        "timed_override": get_config_value(db, "timed_override", "false") == "true",
        "accept_plex_timed_if_plain": get_config_value(db, "accept_plex_timed_if_plain", "false") == "true",
    }


def should_skip_fetch(plex_lyrics_state: str, settings: dict) -> bool:
    """Return True if fetching from external sources can be skipped entirely.

    Only skipped when the user prefers Plex AND Plex already has timed lyrics.
    No Plex Pass → never skip (we don't rely on Plex lyrics at all).
    """
    if not settings["has_plex_pass"]:
        return False
    if settings["lyric_source_preference"] == PREFER_PLEX:
        return plex_lyrics_state == "synced"
    return False  # prefer_lrcplusplus: always attempt fetch


def resolve_lyrics(
    plex_lyrics_state: str,
    our_is_synced: bool | None,
    our_has_content: bool,
    settings: dict,
) -> str:
    """Decide what to do with a track after a fetch attempt.

    Args:
        plex_lyrics_state:  "synced" | "unsynced" | "none"
        our_is_synced:      True if we found timed lyrics, False if plain, None if nothing
        our_has_content:    True if we found any lyrics at all
        settings:           dict from get_lyric_settings()

    Returns:
        USE_OURS       — write our fetched .lrc file
        USE_PLEX       — leave .lrc unwritten; Plex serves its own lyrics
        FLAG_MISSING   — nothing usable found; mark track for attention

    Decision matrix (see PLAN.md for full table):

    No Plex Pass:
        found anything → USE_OURS
        found nothing  → FLAG_MISSING

    Prefer Plex:
        Plex TIMED                          → USE_PLEX (always)
        Plex PLAIN + we have TIMED
          timed_override ON                 → USE_OURS
          timed_override OFF                → USE_PLEX
        Plex PLAIN + we have PLAIN          → USE_PLEX
        Plex PLAIN + we have nothing        → FLAG_MISSING
        Plex NOTHING + we have anything     → USE_OURS
        Plex NOTHING + we have nothing      → FLAG_MISSING

    Prefer LRC++:
        we have TIMED                       → USE_OURS (always)
        we have PLAIN + Plex TIMED
          accept_plex_timed_if_plain ON     → USE_PLEX
          accept_plex_timed_if_plain OFF    → USE_OURS
        we have PLAIN (Plex not timed)      → USE_OURS
        we have nothing                     → FLAG_MISSING
    """
    plex_timed = plex_lyrics_state == "synced"
    plex_plain = plex_lyrics_state == "unsynced"

    # No Plex Pass: ignore Plex entirely
    if not settings["has_plex_pass"]:
        return USE_OURS if our_has_content else FLAG_MISSING

    pref = settings["lyric_source_preference"]

    if pref == PREFER_PLEX:
        if plex_timed:
            return USE_PLEX
        if plex_plain:
            if our_is_synced and settings["timed_override"]:
                return USE_OURS
            if our_has_content and not our_is_synced:
                return USE_PLEX  # Plex plain ties with our plain → Plex wins
            if our_is_synced:
                return USE_PLEX  # timed_override OFF → Plex plain still wins
            return FLAG_MISSING
        # Plex has nothing
        return USE_OURS if our_has_content else FLAG_MISSING

    # PREFER_LRCPLUSPLUS
    if our_is_synced:
        return USE_OURS
    if our_has_content:
        # we have plain text
        if plex_timed and settings["accept_plex_timed_if_plain"]:
            return USE_PLEX
        return USE_OURS
    return FLAG_MISSING


def should_queue_for_review(outcome: str, is_debug: bool) -> bool:
    """Return True if a FLAG_MISSING track should appear in the review queue.

    In debug mode: always queue so the user can inspect what happened.
    In normal/dangerous mode: auto-dismiss — mark as best-available and move on.
    """
    if outcome == FLAG_MISSING:
        return is_debug
    return False
