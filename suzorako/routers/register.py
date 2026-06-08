from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import get_db
from suzorako.services.account_service import get_account, get_account_balance
from suzorako.services.transaction_service import PAGE_SIZE, get_register_rows
from suzorako.utils.money import format_amount, from_decimal

router = APIRouter(tags=["register"])
templates = Jinja2Templates(directory="suzorako/templates")


@router.get("/accounts/{account_id}/register", response_class=HTMLResponse)
async def register_view(account_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    account = await get_account(db, account_id)
    if not account:
        return HTMLResponse("Compte introuvable", status_code=404)
    rows, total_balance = await get_register_rows(db, account_id, offset=0)
    balance_fmt = format_amount(*from_decimal(total_balance))
    return templates.TemplateResponse(request, "accounts/register.html", {
        "account": account,
        "rows": rows,
        "balance": total_balance,
        "balance_fmt": balance_fmt,
        "offset": len(rows),
        "has_more": len(rows) == PAGE_SIZE,
    })


@router.get("/accounts/{account_id}/register/rows", response_class=HTMLResponse)
async def register_rows(account_id: int, request: Request, offset: int = 0, db: AsyncSession = Depends(get_db)):
    rows, _ = await get_register_rows(db, account_id, offset=offset)
    return templates.TemplateResponse(request, "partials/register_rows.html", {
        "account_id": account_id,
        "rows": rows,
        "offset": offset + len(rows),
        "has_more": len(rows) == PAGE_SIZE,
    })
