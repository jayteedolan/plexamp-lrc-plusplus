from dataclasses import dataclass, field
from enum import Enum

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


def get_plex_lyrics_settings(db: Session) -> dict:
    """Return the two Plex-sourced lyrics treatment toggles."""
    return {
        "treat_plex_synced_as_lrc": get_config_value(db, "treat_plex_synced_as_lrc", "true") == "true",
        "treat_plex_unsynced_as_lrc": get_config_value(db, "treat_plex_unsynced_as_lrc", "false") == "true",
    }


def track_needs_fetch(plex_lyrics_state: str, plex_settings: dict) -> bool:
    """Return True if this track still needs lyrics fetched from an external source.

    A track does NOT need fetching if Plex already has lyrics for it AND the
    corresponding toggle is enabled (treating those lyrics as sufficient).
    """
    if plex_lyrics_state == "synced" and plex_settings["treat_plex_synced_as_lrc"]:
        return False
    if plex_lyrics_state == "unsynced" and plex_settings["treat_plex_unsynced_as_lrc"]:
        return False
    return True
