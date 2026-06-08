from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import get_db
from suzorako.services.account_service import (
    ACCOUNT_TYPE_LABELS,
    ACCOUNT_TYPES_ORDER,
    build_account_tree,
    create_account,
    delete_account,
    ensure_default_commodity,
    get_account,
    get_account_balance,
    get_all_accounts,
    get_all_commodities,
    update_account,
)
from suzorako.utils.money import format_amount

router = APIRouter(prefix="/accounts", tags=["accounts"])
templates = Jinja2Templates(directory="suzorako/templates")


@router.get("", response_class=HTMLResponse)
async def account_list(request: Request, db: AsyncSession = Depends(get_db)):
    grouped = await build_account_tree(db)

    # Enrichir avec soldes
    for type_key, accts in grouped.items():
        for acct in accts:
            balance = await get_account_balance(db, acct["id"])
            acct["balance"] = balance
            acct["balance_fmt"] = format_amount(*_decimal_to_frac(balance))

    return templates.TemplateResponse(request, "accounts/list.html", {
        "grouped": grouped,
        "type_labels": ACCOUNT_TYPE_LABELS,
        "types_order": ACCOUNT_TYPES_ORDER,
    })


@router.get("/new", response_class=HTMLResponse)
async def account_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    all_accts = await get_all_accounts(db)
    commodities = await get_all_commodities(db)
    return templates.TemplateResponse(request, "accounts/form.html", {
        "account": None,
        "all_accounts": all_accts,
        "commodities": commodities,
        "types": ACCOUNT_TYPES_ORDER,
        "type_labels": ACCOUNT_TYPE_LABELS,
    })


@router.post("", response_class=HTMLResponse)
async def account_create(
    request: Request,
    name: str = Form(...),
    account_type: str = Form(...),
    commodity_id: int = Form(None),
    parent_id: int = Form(None),
    placeholder: int = Form(0),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not commodity_id:
        commodity_id = await ensure_default_commodity(db)
    await create_account(db, {
        "name": name,
        "account_type": account_type,
        "commodity_id": commodity_id,
        "parent_id": parent_id,
        "placeholder": placeholder,
        "description": description,
    })
    return RedirectResponse("/accounts", status_code=303)


@router.get("/{account_id}/edit", response_class=HTMLResponse)
async def account_edit_form(account_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    acct = await get_account(db, account_id)
    if not acct:
        return HTMLResponse("Compte introuvable", status_code=404)
    all_accts = await get_all_accounts(db)
    commodities = await get_all_commodities(db)
    return templates.TemplateResponse(request, "accounts/form.html", {
        "account": acct,
        "all_accounts": [a for a in all_accts if a["id"] != account_id],
        "commodities": commodities,
        "types": ACCOUNT_TYPES_ORDER,
        "type_labels": ACCOUNT_TYPE_LABELS,
    })


@router.post("/{account_id}", response_class=HTMLResponse)
async def account_update(
    account_id: int,
    request: Request,
    name: str = Form(...),
    account_type: str = Form(...),
    commodity_id: int = Form(None),
    parent_id: int = Form(None),
    placeholder: int = Form(0),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    await update_account(db, account_id, {
        "name": name,
        "account_type": account_type,
        "commodity_id": commodity_id,
        "parent_id": parent_id,
        "placeholder": placeholder,
        "description": description,
    })
    return RedirectResponse("/accounts", status_code=303)


@router.delete("/{account_id}", response_class=HTMLResponse)
async def account_delete(account_id: int, db: AsyncSession = Depends(get_db)):
    await delete_account(db, account_id)
    return HTMLResponse("")


def _decimal_to_frac(d):
    from suzorako.utils.money import from_decimal
    return from_decimal(d)
