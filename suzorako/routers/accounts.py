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
from suzorako.services.validation import (
    ValidationError,
    get_descendant_ids,
    validate_account_parent,
)
from suzorako.utils.money import format_amount, from_decimal

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
            acct["balance_fmt"] = format_amount(*from_decimal(balance))

    return templates.TemplateResponse(request, "accounts/list.html", {
        "grouped": grouped,
        "type_labels": ACCOUNT_TYPE_LABELS,
        "types_order": ACCOUNT_TYPES_ORDER,
    })


async def _render_form(
    request: Request,
    db: AsyncSession,
    *,
    account: dict | None,
    values: dict,
    error: str | None = None,
    status_code: int = 200,
):
    all_accts = await get_all_accounts(db)
    if account is not None:
        # Exclure le compte lui-même et ses descendants (anti-cycle) des parents possibles.
        excluded = await get_descendant_ids(db, account["id"])
        all_accts = [a for a in all_accts if a["id"] not in excluded]
    commodities = await get_all_commodities(db)
    return templates.TemplateResponse(request, "accounts/form.html", {
        "account": account,
        "values": values,
        "error": error,
        "all_accounts": all_accts,
        "commodities": commodities,
        "types": ACCOUNT_TYPES_ORDER,
        "type_labels": ACCOUNT_TYPE_LABELS,
    }, status_code=status_code)


def _values_from_form(name, account_type, parent_id, commodity_id, placeholder, description) -> dict:
    return {
        "name": name,
        "account_type": account_type,
        "parent_id": parent_id,
        "commodity_id": commodity_id,
        "placeholder": placeholder,
        "description": description,
    }


def _values_from_account(acct: dict) -> dict:
    return {
        "name": acct["name"],
        "account_type": acct["account_type"],
        "parent_id": acct["parent_id"],
        "commodity_id": acct["commodity_id"],
        "placeholder": acct["placeholder"],
        "description": acct["description"],
    }


@router.get("/new", response_class=HTMLResponse)
async def account_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    values = _values_from_form("", "", None, None, 0, "")
    return await _render_form(request, db, account=None, values=values)


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
    values = _values_from_form(name, account_type, parent_id, commodity_id, placeholder, description)
    try:
        await validate_account_parent(db, account_type=account_type, parent_id=parent_id)
    except ValidationError as e:
        return await _render_form(request, db, account=None, values=values, error=str(e), status_code=422)

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
    return await _render_form(request, db, account=acct, values=_values_from_account(acct))


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
    values = _values_from_form(name, account_type, parent_id, commodity_id, placeholder, description)
    acct = await get_account(db, account_id)
    if not acct:
        return HTMLResponse("Compte introuvable", status_code=404)
    try:
        await validate_account_parent(
            db, account_type=account_type, parent_id=parent_id, account_id=account_id
        )
    except ValidationError as e:
        return await _render_form(request, db, account=acct, values=values, error=str(e), status_code=422)

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
