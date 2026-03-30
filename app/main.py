from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal, create_tables
from app.mode_config import get_config_value


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    _seed_default_config()
    # Worker scheduler is started here once implemented
    yield


def _seed_default_config() -> None:
    """Insert default config keys if they don't exist yet."""
    from app.mode_config import set_config_value
    db = SessionLocal()
    try:
        defaults = {
            "operating_mode": "normal",
            "dangerous_threshold": "high",
            "setup_complete": "false",
            "has_plex_pass": "true",
            "lyric_source_preference": "prefer_plex",
            "timed_override": "false",
            "accept_plex_timed_if_plain": "false",
        }
        for key, value in defaults.items():
            from app.models import Config
            if not db.get(Config, key):
                set_config_value(db, key, value)
    finally:
        db.close()


app = FastAPI(title="Plexamp LRC++", lifespan=lifespan)

# Static files
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# --- Routers (imported here to avoid circular imports) ---
from app.routers import dashboard, wizard  # noqa: E402

app.include_router(wizard.router)
app.include_router(dashboard.router)


# --- Root redirect ---
@app.get("/")
async def root():
    """Redirect to setup wizard if not configured, otherwise to onboarding."""
    db = SessionLocal()
    try:
        setup_complete = get_config_value(db, "setup_complete", "false")
    finally:
        db.close()

    if setup_complete != "true":
        return RedirectResponse(url="/setup", status_code=302)

    return RedirectResponse(url="/onboarding", status_code=302)
