import io
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.utils.money import from_decimal


async def parse_ofx(
    content: bytes,
    account_map: dict[str, int],
    db: AsyncSession,
) -> tuple[list[dict], str]:
    """
    Parse un fichier OFX bancaire.
    Chaque STMTTRN devient une transaction à 2 splits :
      - compte bancaire (identifié par ACCTID ou choisi par l'utilisateur)
      - compte Imbalance (à catégoriser)
    """
    import ofxparse

    ofx = ofxparse.OfxParser.parse(io.BytesIO(content))
    import_id = str(uuid.uuid4())[:8]
    preview = []

    # Trouver un compte Imbalance (fallback)
    imbalance_id = account_map.get("Imbalance") or account_map.get("Imbalance-EUR")

    # Compte bancaire : chercher par ACCTID dans les noms de comptes
    bank_account_id: int | None = None
    if hasattr(ofx, "account") and ofx.account:
        acct_id = getattr(ofx.account, "account_id", "")
        bank_account_id = account_map.get(acct_id)

    for stmt in (ofx.account.statement,) if hasattr(ofx, "account") else []:
        for txn in stmt.transactions:
            fitid = txn.id
            # Dédup : ne pas importer si external_id déjà présent
            if await _fitid_exists(db, fitid):
                continue

            date_str = txn.date.strftime("%Y-%m-%d") if txn.date else ""
            desc = (txn.memo or txn.payee or "").strip()
            amount = Decimal(str(txn.amount))
            num, denom = from_decimal(amount)

            splits = [
                {
                    "account_id": bank_account_id,
                    "account_name": "Compte bancaire",
                    "value_num": num,
                    "value_denom": denom,
                    "memo": "",
                    "external_id": fitid,
                },
                {
                    "account_id": imbalance_id,
                    "account_name": "Imbalance (à catégoriser)",
                    "value_num": -num,
                    "value_denom": denom,
                    "memo": "",
                    "external_id": None,
                },
            ]

            preview.append({
                "post_date": date_str,
                "description": desc,
                "notes": f"FITID:{fitid}",
                "splits": splits,
                "is_duplicate": False,
            })

    return preview, import_id


async def _fitid_exists(db: AsyncSession, fitid: str) -> bool:
    result = await db.execute(
        text("SELECT 1 FROM splits WHERE external_id = :fitid LIMIT 1"),
        {"fitid": fitid},
    )
    return result.first() is not None
