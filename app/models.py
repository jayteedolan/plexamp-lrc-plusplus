from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plex_track_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    plex_section_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    title: Mapped[str] = mapped_column(String, default="")
    artist: Mapped[str] = mapped_column(String, default="")
    album_artist: Mapped[str] = mapped_column(String, default="")
    album: Mapped[str] = mapped_column(String, default="")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    file_path: Mapped[str] = mapped_column(String, default="")
    lrc_path: Mapped[str] = mapped_column(String, default="")

    # pending / approved / rejected / missing / has_lrc / error
    lyrics_status: Mapped[str] = mapped_column(String, default="pending")
    # lrclib / syncedlyrics / genius / manual
    lyrics_source: Mapped[str | None] = mapped_column(String, nullable=True)
    lyrics_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # unreviewed / approved / rejected / skipped
    onboarding_status: Mapped[str] = mapped_column(String, default="unreviewed")

    # Plex-sourced lyrics detected during library scan
    # none / synced / unsynced
    plex_lyrics_state: Mapped[str] = mapped_column(String, default="none")

    # Debug mode: raw API responses + confidence breakdown (JSON)
    debug_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dangerously-accept mode: groups a bulk-approval run for undo
    batch_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lrc_written_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plex_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    album_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("albums.id"), nullable=True)
    album_rel: Mapped["Album | None"] = relationship("Album", back_populates="tracks")
    log_entries: Mapped[list["ActivityLog"]] = relationship("ActivityLog", back_populates="track")


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artist: Mapped[str] = mapped_column(String, default="")
    album: Mapped[str] = mapped_column(String, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # not_started / in_progress / complete / skipped
    onboarding_status: Mapped[str] = mapped_column(String, default="not_started")

    track_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    tracks: Mapped[list["Track"]] = relationship("Track", back_populates="album_rel")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # info / warning / error / success
    level: Mapped[str] = mapped_column(String, default="info")
    # scan / fetch / write / plex_refresh / onboarding / system
    category: Mapped[str] = mapped_column(String, default="system")
    message: Mapped[str] = mapped_column(String, default="")

    track_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tracks.id"), nullable=True)
    track: Mapped["Track | None"] = relationship("Track", back_populates="log_entries")


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
