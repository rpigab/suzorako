from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
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
from suzorako.services.validation import (
    BALANCE_TOLERANCE,
    ValidationError,
    assert_postable,
    balance_splits,
)
from suzorako.utils.money import to_decimal

router = APIRouter(tags=["transactions"])
templates = Jinja2Templates(directory="suzorako/templates")


def _empty_rows(prefill_account_id: int | None) -> list[dict]:
    return [
        {"account_id": prefill_account_id, "amount_str": "", "memo": ""},
        {"account_id": None, "amount_str": "", "memo": ""},
    ]


def _rows_from_transaction(txn: dict) -> list[dict]:
    rows = []
    for sp in txn["splits"]:
        amount = to_decimal(sp["value_num"], sp["value_denom"])
        rows.append({
            "account_id": sp["account_id"],
            "amount_str": f"{amount:.2f}",
            "memo": sp.get("memo", ""),
        })
    return rows


def _parse_raw_splits(form) -> list[dict]:
    """Extrait les ventilations brutes du formulaire (montant éventuellement vide)."""
    raw = []
    idx = 0
    while f"split_account_{idx}" in form:
        account_id = form.get(f"split_account_{idx}")
        amount_str = (form.get(f"split_amount_{idx}") or "").replace(",", ".").replace(" ", "").strip()
        amount = None
        if amount_str:
            try:
                amount = Decimal(amount_str)
            except Exception:
                amount = None
        raw.append({
            "account_id": int(account_id) if account_id else None,
            "amount": amount,
            "amount_str": form.get(f"split_amount_{idx}", ""),
            "memo": form.get(f"split_memo_{idx}", ""),
        })
        idx += 1
    return raw


async def _render_form(
    request: Request,
    db: AsyncSession,
    *,
    transaction: dict | None,
    values: dict,
    split_rows: list[dict],
    redirect_account_id: int | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    all_accts = await get_all_accounts(db)
    descriptions = await get_recent_descriptions(db)
    return templates.TemplateResponse(request, "transactions/form.html", {
        "transaction": transaction,
        "values": values,
        "split_rows": split_rows,
        "redirect_account_id": redirect_account_id,
        "all_accounts": all_accts,
        "descriptions": descriptions,
        "error": error,
    }, status_code=status_code)


@router.get("/transactions/new", response_class=HTMLResponse)
async def transaction_new_form(
    request: Request,
    account_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    values = {"post_date": date.today().isoformat(), "description": "", "notes": ""}
    return await _render_form(
        request, db,
        transaction=None,
        values=values,
        split_rows=_empty_rows(account_id),
        redirect_account_id=account_id,
    )


@router.get("/transactions/{txn_id}/edit", response_class=HTMLResponse)
async def transaction_edit_form(txn_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    txn = await get_transaction(db, txn_id)
    if not txn:
        return HTMLResponse("Transaction introuvable", status_code=404)
    values = {"post_date": txn["post_date"], "description": txn["description"], "notes": txn["notes"]}
    return await _render_form(
        request, db,
        transaction=txn,
        values=values,
        split_rows=_rows_from_transaction(txn),
    )


@router.post("/transactions", response_class=HTMLResponse)
async def transaction_create(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    raw = _parse_raw_splits(form)
    values = {
        "post_date": form.get("post_date", ""),
        "description": form.get("description", ""),
        "notes": form.get("notes", ""),
    }
    redirect_account = form.get("redirect_account_id")
    redirect_account_id = int(redirect_account) if redirect_account else None

    try:
        splits_data = balance_splits(raw)
        await assert_postable(db, [s["account_id"] for s in splits_data])
    except ValidationError as e:
        return await _render_form(
            request, db, transaction=None, values=values,
            split_rows=_rows_from_raw(raw, redirect_account_id),
            redirect_account_id=redirect_account_id, error=str(e), status_code=422,
        )

    commodity_id = await ensure_default_commodity(db)
    await create_transaction(db, {
        "post_date": values["post_date"],
        "description": values["description"],
        "notes": values["notes"],
        "commodity_id": commodity_id,
        "splits": splits_data,
    })

    if redirect_account_id:
        return RedirectResponse(f"/accounts/{redirect_account_id}/register", status_code=303)
    return RedirectResponse("/accounts", status_code=303)


@router.post("/transactions/{txn_id}", response_class=HTMLResponse)
async def transaction_update(txn_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    txn = await get_transaction(db, txn_id)
    if not txn:
        return HTMLResponse("Transaction introuvable", status_code=404)
    raw = _parse_raw_splits(form)
    values = {
        "post_date": form.get("post_date", ""),
        "description": form.get("description", ""),
        "notes": form.get("notes", ""),
    }
    redirect_account = form.get("redirect_account_id")
    redirect_account_id = int(redirect_account) if redirect_account else None

    try:
        splits_data = balance_splits(raw)
        await assert_postable(db, [s["account_id"] for s in splits_data])
    except ValidationError as e:
        return await _render_form(
            request, db, transaction=txn, values=values,
            split_rows=_rows_from_raw(raw, redirect_account_id),
            redirect_account_id=redirect_account_id, error=str(e), status_code=422,
        )

    await update_transaction(db, txn_id, {
        "post_date": values["post_date"],
        "description": values["description"],
        "notes": values["notes"],
        "splits": splits_data,
    })
    if redirect_account_id:
        return RedirectResponse(f"/accounts/{redirect_account_id}/register", status_code=303)
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
    raw = _parse_raw_splits(form)
    entries = [s for s in raw if s["account_id"]]
    blanks = [s for s in entries if s["amount"] is None]
    known = sum((s["amount"] for s in entries if s["amount"] is not None), Decimal("0"))

    if len(entries) < 2:
        cls, msg = "unbalanced", "Ajoutez au moins deux ventilations."
    elif len(blanks) == 1:
        cls, msg = "balanced", f"Équilibrage automatique : {-known:+.2f} € sur la ventilation vide."
    elif len(blanks) > 1:
        cls, msg = "unbalanced", "Laissez au plus une ventilation vide pour l'équilibrage auto."
    elif abs(known) <= BALANCE_TOLERANCE:
        cls, msg = "balanced", "Équilibré ✓"
    else:
        cls, msg = "unbalanced", f"Déséquilibre : {known:+.2f} €"

    return HTMLResponse(
        f'<div id="imbalance-indicator" class="imbalance-indicator {cls}">{msg}</div>'
    )


def _rows_from_raw(raw: list[dict], prefill_account_id: int | None) -> list[dict]:
    rows = [
        {"account_id": s["account_id"], "amount_str": s["amount_str"], "memo": s["memo"]}
        for s in raw
    ]
    return rows or _empty_rows(prefill_account_id)
