from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.web.dashboard_data import get_macro_dashboard, get_market_calendar, get_sector_dashboard


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="StockAgent Web")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/macro", status_code=307)


@app.get("/macro")
def macro_page(request: Request):
    dashboard = get_macro_dashboard()
    return templates.TemplateResponse(
        "macro.html",
        {
            "request": request,
            "active_page": "macro",
            "dashboard": dashboard,
        },
    )


@app.get("/sectors")
def sectors_page(request: Request, market: Literal["US", "KR"] = Query(default="US")):
    dashboard = get_sector_dashboard(market)
    return templates.TemplateResponse(
        "sectors.html",
        {
            "request": request,
            "active_page": "sectors",
            "dashboard": dashboard,
        },
    )


@app.get("/calendar")
def calendar_page(request: Request, start: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    calendar = get_market_calendar(start=start)
    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "active_page": "calendar",
            "calendar": calendar,
        },
    )
