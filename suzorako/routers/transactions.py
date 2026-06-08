from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import get_db
from suzorako.services.account_service import ensure_default_commodity, get_all_accounts
from suzorako.services.transaction_service import (
    create_transaction,
    delete_transaction,
    get_recent_descriptions,
    get_transaction,
    toggle_reconcile,
    update_transaction,
)
from suzorako.utils.money import from_decimal

router = APIRouter(tags=["transactions"])
templates = Jinja2Templates(directory="suzorako/templates")


@router.get("/transactions/new", response_class=HTMLResponse)
async def transaction_new_form(
    request: Request,
    account_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    all_accts = await get_all_accounts(db)
    descriptions = await get_recent_descriptions(db)
    return templates.TemplateResponse(request, "transactions/form.html", {
        "transaction": None,
        "all_accounts": all_accts,
        "descriptions": descriptions,
        "prefill_account_id": account_id,
    })


@router.get("/transactions/{txn_id}/edit", response_class=HTMLResponse)
async def transaction_edit_form(txn_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    txn = await get_transaction(db, txn_id)
    if not txn:
        return HTMLResponse("Transaction introuvable", status_code=404)
    all_accts = await get_all_accounts(db)
    descriptions = await get_recent_descriptions(db)
    return templates.TemplateResponse(request, "transactions/form.html", {
        "transaction": txn,
        "all_accounts": all_accts,
        "descriptions": descriptions,
        "prefill_account_id": None,
    })


@router.post("/transactions", response_class=HTMLResponse)
async def transaction_create(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    commodity_id = await ensure_default_commodity(db)
    splits_data = _parse_splits_form(form)

    if not splits_data:
        return HTMLResponse("Au moins deux ventilations sont requises.", status_code=422)

    redirect_account = form.get("redirect_account_id")
    await create_transaction(db, {
        "post_date": form["post_date"],
        "description": form["description"],
        "notes": form.get("notes", ""),
        "commodity_id": commodity_id,
        "splits": splits_data,
    })

    if redirect_account:
        return RedirectResponse(f"/accounts/{redirect_account}/register", status_code=303)
    return RedirectResponse("/accounts", status_code=303)


@router.post("/transactions/{txn_id}", response_class=HTMLResponse)
async def transaction_update(txn_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    splits_data = _parse_splits_form(form)
    redirect_account = form.get("redirect_account_id")
    await update_transaction(db, txn_id, {
        "post_date": form["post_date"],
        "description": form["description"],
        "notes": form.get("notes", ""),
        "splits": splits_data,
    })
    if redirect_account:
        return RedirectResponse(f"/accounts/{redirect_account}/register", status_code=303)
    return RedirectResponse("/accounts", status_code=303)


@router.delete("/transactions/{txn_id}", response_class=HTMLResponse)
async def transaction_delete(txn_id: int, db: AsyncSession = Depends(get_db)):
    await delete_transaction(db, txn_id)
    return HTMLResponse("")


@router.post("/splits/{split_id}/reconcile", response_class=HTMLResponse)
async def split_reconcile(split_id: int, db: AsyncSession = Depends(get_db)):
    state = await toggle_reconcile(db, split_id)
    icons = {"n": "○", "c": "◐", "y": "●"}
    return HTMLResponse(
        f'<button hx-post="/splits/{split_id}/reconcile" '
        f'hx-target="this" hx-swap="outerHTML" '
        f'class="reconcile-btn" title="{state}">{icons[state]}</button>'
    )


@router.post("/transactions/check-balance", response_class=HTMLResponse)
async def check_balance(request: Request):
    form = await request.form()
    splits_data = _parse_splits_form(form)
    total = sum(
        Decimal(sp["value_num"]) / Decimal(sp["value_denom"])
        for sp in splits_data
    )
    balanced = abs(total) < Decimal("0.01")
    cls = "balanced" if balanced else "unbalanced"
    msg = "Équilibré ✓" if balanced else f"Déséquilibre : {total:+.2f} €"
    return HTMLResponse(f'<div id="imbalance-indicator" class="imbalance-indicator {cls}">{msg}</div>')


def _parse_splits_form(form) -> list[dict]:
    """Extrait les splits depuis les champs de formulaire nommés split_account_N, split_amount_N."""
    splits = []
    idx = 0
    while True:
        account_key = f"split_account_{idx}"
        amount_key = f"split_amount_{idx}"
        if account_key not in form:
            break
        account_id = form.get(account_key)
        amount_str = form.get(amount_key, "").replace(",", ".").strip()
        if account_id and amount_str:
            try:
                amount = Decimal(amount_str)
                num, denom = from_decimal(amount)
                splits.append({
                    "account_id": int(account_id),
                    "value_num": num,
                    "value_denom": denom,
                    "memo": form.get(f"split_memo_{idx}", ""),
                })
            except Exception:
                pass
        idx += 1
    return splits
