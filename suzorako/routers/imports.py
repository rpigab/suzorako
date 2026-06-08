from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import get_db
from suzorako.services.account_service import ensure_default_commodity, get_all_accounts
from suzorako.services.import_csv import parse_gnucash_csv
from suzorako.services.import_ofx import parse_ofx
from suzorako.services.transaction_service import create_transaction

router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="suzorako/templates")

# Stockage en mémoire des transactions en attente de confirmation (simple, per-process)
_pending_imports: dict[str, list[dict]] = {}


@router.get("", response_class=HTMLResponse)
async def import_view(request: Request, db: AsyncSession = Depends(get_db)):
    all_accts = await get_all_accounts(db)
    return templates.TemplateResponse(request, "import/index.html", {
        "all_accounts": all_accts,
    })


@router.post("/csv", response_class=HTMLResponse)
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    all_accts = await get_all_accounts(db)
    account_map = {a["name"]: a["id"] for a in all_accts}
    try:
        preview, import_id = await parse_gnucash_csv(content, account_map, db)
    except Exception as e:
        return HTMLResponse(f'<p style="color:red;">Erreur de parsing : {e}</p>')
    _pending_imports[import_id] = preview
    return templates.TemplateResponse(request, "partials/import_preview.html", {
        "preview": preview,
        "import_id": import_id,
        "all_accounts": all_accts,
        "source": "csv",
    })


@router.post("/ofx", response_class=HTMLResponse)
async def import_ofx(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    all_accts = await get_all_accounts(db)
    account_map = {a["name"]: a["id"] for a in all_accts}
    try:
        preview, import_id = await parse_ofx(content, account_map, db)
    except Exception as e:
        return HTMLResponse(f'<p style="color:red;">Erreur de parsing : {e}</p>')
    _pending_imports[import_id] = preview
    return templates.TemplateResponse(request, "partials/import_preview.html", {
        "preview": preview,
        "import_id": import_id,
        "all_accounts": all_accts,
        "source": "ofx",
    })


@router.post("/confirm", response_class=HTMLResponse)
async def import_confirm(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    import_id = form.get("import_id")
    selected_indices = form.getlist("import_select")
    selected_set = set(int(i) for i in selected_indices)

    pending = _pending_imports.get(import_id, [])
    commodity_id = await ensure_default_commodity(db)
    imported = 0

    for i, txn in enumerate(pending):
        if i not in selected_set:
            continue
        # Résoudre les account_ids depuis le formulaire (peuvent avoir été changés par l'utilisateur)
        splits = []
        for j, sp in enumerate(txn["splits"]):
            acct_key = f"account_{import_id}_{i}_{j}"
            account_id = int(form.get(acct_key, sp["account_id"] or 0))
            if not account_id:
                continue
            splits.append({
                "account_id": account_id,
                "value_num": sp["value_num"],
                "value_denom": sp["value_denom"],
                "memo": sp.get("memo", ""),
                "external_id": sp.get("external_id"),
            })
        if len(splits) >= 2:
            await create_transaction(db, {
                "post_date": txn["post_date"],
                "description": txn["description"],
                "notes": txn.get("notes", ""),
                "commodity_id": commodity_id,
                "splits": splits,
            })
            imported += 1

    _pending_imports.pop(import_id, None)
    return HTMLResponse(
        f'<p style="color:green;">✓ {imported} transaction(s) importée(s). '
        f'<a href="/accounts">Voir les comptes</a></p>'
    )
