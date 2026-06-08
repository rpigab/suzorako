import csv
import io
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.utils.money import from_decimal


async def parse_gnucash_csv(
    content: bytes,
    account_map: dict[str, int],
    db: AsyncSession,
) -> tuple[list[dict], str]:
    """
    Parse un export CSV GnuCash (format 'transaction with splits').
    Retourne (liste de PreviewTransaction, import_id).
    """
    text_content = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))
    rows = list(reader)

    # Grouper par (Date, Description) ou par un GUID de transaction si présent
    groups: dict[str, list] = {}
    for row in rows:
        date = row.get("Date", "").strip()
        desc = row.get("Description", "").strip()
        # Certains exports GnuCash ont un champ Transaction ID
        txn_key = row.get("Transaction ID", "") or f"{date}|{desc}"
        if txn_key not in groups:
            groups[txn_key] = []
        groups[txn_key].append(row)

    import_id = str(uuid.uuid4())[:8]
    preview = []

    for txn_key, split_rows in groups.items():
        first = split_rows[0]
        date_str = _parse_date(first.get("Date", ""))
        if not date_str:
            continue
        desc = first.get("Description", "").strip()

        splits = []
        for row in split_rows:
            account_name = row.get("Full Account Name", row.get("Account Name", "")).strip()
            account_id = account_map.get(account_name)
            # Montant : GnuCash utilise "Value Num" / "Value Denom" ou "Amount Num" / "Amount Denom"
            value_num, value_denom = _parse_value(row)
            splits.append({
                "account_id": account_id,
                "account_name": account_name,
                "value_num": value_num,
                "value_denom": value_denom,
                "memo": row.get("Memo", "").strip(),
            })

        # Détection doublons
        is_duplicate = await _check_duplicate(db, date_str, desc)

        preview.append({
            "post_date": date_str,
            "description": desc,
            "notes": first.get("Notes", "").strip(),
            "splits": splits,
            "is_duplicate": is_duplicate,
        })

    return preview, import_id


def _parse_date(raw: str) -> str | None:
    """Normalise diverses formats de date vers YYYY-MM-DD."""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_value(row: dict) -> tuple[int, int]:
    """Extrait value_num, value_denom depuis une ligne CSV GnuCash."""
    # Format "Value Num" / "Value Denom"
    if "Value Num" in row and "Value Denom" in row:
        try:
            return int(row["Value Num"]), int(row["Value Denom"])
        except (ValueError, TypeError):
            pass
    # Fallback : colonne "Amount" en virgule flottante
    amount_str = row.get("Amount", row.get("Value", "0")).replace(",", ".").replace(" ", "")
    try:
        amount = Decimal(amount_str)
        return from_decimal(amount)
    except Exception:
        return 0, 100


async def _check_duplicate(db: AsyncSession, post_date: str, description: str) -> bool:
    result = await db.execute(
        text("SELECT 1 FROM transactions WHERE post_date = :d AND description = :desc LIMIT 1"),
        {"d": post_date, "desc": description},
    )
    return result.first() is not None
