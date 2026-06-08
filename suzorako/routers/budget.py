from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import get_db
from suzorako.services.budget_service import get_chart_data, get_budget_table

router = APIRouter(prefix="/budget", tags=["budget"])
templates = Jinja2Templates(directory="suzorako/templates")


@router.get("", response_class=HTMLResponse)
async def budget_view(request: Request, year: int = None, period: str = "monthly"):
    from datetime import date
    if not year:
        year = date.today().year
    return templates.TemplateResponse(request, "budget/index.html", {
        "year": year,
        "period": period,
    })


@router.get("/chart-data")
async def chart_data(year: int = None, period: str = "monthly", db: AsyncSession = Depends(get_db)):
    from datetime import date
    if not year:
        year = date.today().year
    data = await get_chart_data(db, year, period)
    return JSONResponse(data)


@router.get("/table", response_class=HTMLResponse)
async def budget_table(request: Request, year: int = None, period: str = "monthly", db: AsyncSession = Depends(get_db)):
    from datetime import date
    if not year:
        year = date.today().year
    rows = await get_budget_table(db, year)
    return templates.TemplateResponse(request, "partials/budget_table.html", {
        "rows": rows,
        "year": year,
        "period": period,
    })
