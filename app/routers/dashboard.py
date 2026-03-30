from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.mode_config import get_config_value, get_mode_config

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    mode_config = get_mode_config(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "mode": mode_config.mode.value,
        },
    )


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_placeholder(request: Request, db: Session = Depends(get_db)):
    mode_config = get_mode_config(db)
    plex_url = get_config_value(db, "plex_url")
    return templates.TemplateResponse(
        "onboarding_placeholder.html",
        {
            "request": request,
            "active": "onboarding",
            "mode": mode_config.mode.value,
            "plex_url": plex_url,
        },
    )
