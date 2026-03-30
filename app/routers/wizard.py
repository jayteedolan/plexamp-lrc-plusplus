from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.mode_config import get_config_value, set_config_value
from app.plex_client import get_music_libraries, test_connection

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))

STEPS = ["Welcome", "Connection", "Library", "Mode", "Confirm"]


def _step_context(step: int, **kwargs) -> dict:
    return {"steps": STEPS, "current_step": step, **kwargs}


# ── Step 1: Welcome ────────────────────────────────────────────────────────────

@router.get("/setup", response_class=HTMLResponse)
async def wizard_start(request: Request, db: Session = Depends(get_db)):
    if get_config_value(db, "setup_complete") == "true":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "wizard.html",
        {"request": request, **_step_context(1)},
    )


@router.get("/setup/rerun", response_class=HTMLResponse)
async def wizard_rerun(request: Request, db: Session = Depends(get_db)):
    """Re-run the wizard from the beginning, pre-populating existing config."""
    existing = {
        "plex_url": get_config_value(db, "plex_url"),
        "plex_library_name": get_config_value(db, "plex_library_name", "Music"),
        "music_dir": get_config_value(db, "music_dir"),
        "operating_mode": get_config_value(db, "operating_mode", "normal"),
        "dangerous_threshold": get_config_value(db, "dangerous_threshold", "high"),
    }
    return templates.TemplateResponse(
        "wizard.html",
        {"request": request, **_step_context(1), "existing": existing},
    )


# ── Step 2 fragment: Connection form ──────────────────────────────────────────

@router.get("/setup/step/connection", response_class=HTMLResponse)
async def wizard_step_connection(request: Request, db: Session = Depends(get_db)):
    existing = {
        "plex_url": get_config_value(db, "plex_url"),
    }
    return templates.TemplateResponse(
        "wizard_fragments/step_connection.html",
        {"request": request, **_step_context(2), "existing": existing},
    )


# ── HTMX: Test Plex connection ────────────────────────────────────────────────

@router.post("/setup/test-plex", response_class=HTMLResponse)
async def wizard_test_plex(
    request: Request,
    plex_url: str = Form(...),
    plex_token: str = Form(...),
):
    ok, message = test_connection(plex_url.strip(), plex_token.strip())
    css_class = "ok" if ok else "err"
    prefix = "✓" if ok else "✗"
    return HTMLResponse(
        f'<span id="connection-result" class="{css_class}">{prefix} {message}</span>'
        + (
            f'<input type="hidden" name="_connection_ok" value="true" />'
            if ok else ""
        )
    )


# ── HTMX: Library dropdown (called after successful connection test) ──────────

@router.post("/setup/libraries", response_class=HTMLResponse)
async def wizard_libraries(
    request: Request,
    plex_url: str = Form(...),
    plex_token: str = Form(...),
):
    libraries = get_music_libraries(plex_url.strip(), plex_token.strip())
    options = "\n".join(
        f'<option value="{lib["title"]}">{lib["title"]}</option>'
        for lib in libraries
    )
    if not options:
        options = '<option value="Music">Music</option>'
    return HTMLResponse(f'<select id="library-select" name="plex_library_name" class="form-control">{options}</select>')


# ── Step fragment loaders (HTMX next-step navigation) ────────────────────────

@router.get("/setup/step/{step_num}", response_class=HTMLResponse)
async def wizard_step(step_num: int, request: Request, db: Session = Depends(get_db)):
    templates_map = {
        3: "wizard_fragments/step_library.html",
        4: "wizard_fragments/step_mode.html",
        5: "wizard_fragments/step_confirm.html",
    }
    if step_num not in templates_map:
        return HTMLResponse("", status_code=404)
    existing = {
        "plex_library_name": get_config_value(db, "plex_library_name", "Music"),
        "music_dir": get_config_value(db, "music_dir"),
        "operating_mode": get_config_value(db, "operating_mode", "normal"),
        "dangerous_threshold": get_config_value(db, "dangerous_threshold", "high"),
        "treat_plex_synced_as_lrc": get_config_value(db, "treat_plex_synced_as_lrc", "true"),
        "treat_plex_unsynced_as_lrc": get_config_value(db, "treat_plex_unsynced_as_lrc", "false"),
    }
    return templates.TemplateResponse(
        templates_map[step_num],
        {"request": request, **_step_context(step_num), "existing": existing},
    )


# ── Final save ────────────────────────────────────────────────────────────────

@router.post("/setup/save")
async def wizard_save(
    request: Request,
    db: Session = Depends(get_db),
    plex_url: str = Form(...),
    plex_token: str = Form(...),
    plex_library_name: str = Form("Music"),
    music_dir: str = Form(""),
    operating_mode: str = Form("normal"),
    dangerous_threshold: str = Form("high"),
    treat_plex_synced_as_lrc: str = Form("false"),
    treat_plex_unsynced_as_lrc: str = Form("false"),
):
    set_config_value(db, "plex_url", plex_url.strip())
    set_config_value(db, "plex_token", plex_token.strip())
    set_config_value(db, "plex_library_name", plex_library_name.strip())
    set_config_value(db, "music_dir", music_dir.strip())
    set_config_value(db, "operating_mode", operating_mode)
    set_config_value(db, "dangerous_threshold", dangerous_threshold)
    # Checkboxes only send a value when checked; treat absence as "false"
    set_config_value(db, "treat_plex_synced_as_lrc", "true" if treat_plex_synced_as_lrc == "true" else "false")
    set_config_value(db, "treat_plex_unsynced_as_lrc", "true" if treat_plex_unsynced_as_lrc == "true" else "false")
    set_config_value(db, "setup_complete", "true")

    # Trigger initial library scan (worker will be wired up in a later slice)
    # TODO: scheduler.add_job(sync_library, 'date', ...)

    return RedirectResponse(url="/onboarding", status_code=303)
