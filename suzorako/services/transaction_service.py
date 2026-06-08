import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import accounts, splits, transactions
from suzorako.utils.money import from_decimal, to_decimal

PAGE_SIZE = 50


async def get_register_rows(db: AsyncSession, account_id: int, offset: int = 0) -> list[dict]:
    """Retourne les lignes du registre pour un compte, paginées."""
    result = await db.execute(
        text("""
            SELECT
                t.id as transaction_id,
                t.post_date,
                t.description,
                s.id as split_id,
                s.memo,
                s.value_num,
                s.value_denom,
                s.reconcile_state,
                a.name as transfer_account
            FROM splits s
            JOIN transactions t ON s.transaction_id = t.id
            JOIN accounts a2 ON s.account_id = a2.id
            LEFT JOIN (
                SELECT s2.transaction_id, GROUP_CONCAT(a3.name, ', ') as name
                FROM splits s2
                JOIN accounts a3 ON s2.account_id = a3.id
                WHERE s2.account_id != :account_id
                GROUP BY s2.transaction_id
            ) other ON other.transaction_id = t.id
            LEFT JOIN accounts a ON a.id = (
                SELECT s3.account_id FROM splits s3
                WHERE s3.transaction_id = t.id AND s3.account_id != :account_id
                LIMIT 1
            )
            WHERE s.account_id = :account_id
            ORDER BY t.post_date DESC, t.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {"account_id": account_id, "limit": PAGE_SIZE, "offset": offset},
    )
    rows = [dict(r._mapping) for r in result]

    # Calculer le solde courant (simplifié : solde total - somme des transactions après offset)
    balance_result = await db.execute(
        text("""
            SELECT COALESCE(SUM(CAST(value_num AS REAL) / value_denom), 0)
            FROM splits WHERE account_id = :account_id
        """),
        {"account_id": account_id},
    )
    total_balance = Decimal(str(balance_result.scalar()))

    # Solde des transactions au-delà du offset (pour calcul de solde running)
    # On calcule un running balance approximatif
    for i, row in enumerate(rows):
        row["amount"] = to_decimal(row["value_num"], row["value_denom"])
        row["amount_fmt"] = _fmt(row["amount"])

    return rows, total_balance


async def get_recent_descriptions(db: AsyncSession, q: str = "") -> list[str]:
    result = await db.execute(
        text("""
            SELECT DISTINCT description FROM transactions
            WHERE description LIKE :q
            ORDER BY post_date DESC
            LIMIT 20
        """),
        {"q": f"%{q}%"},
    )
    return [r[0] for r in result]


async def create_transaction(db: AsyncSession, data: dict) -> int:
    """
    data = {
        post_date: str (YYYY-MM-DD),
        description: str,
        notes: str,
        commodity_id: int,
        splits: [{ account_id, value_num, value_denom, memo }]
    }
    """
    txn_guid = str(uuid.uuid4())
    enter_date = datetime.utcnow().isoformat()

    result = await db.execute(
        insert(transactions).values(
            guid=txn_guid,
            post_date=data["post_date"],
            enter_date=enter_date,
            description=data["description"],
            notes=data.get("notes", ""),
            commodity_id=data.get("commodity_id"),
        ).returning(transactions.c.id)
    )
    txn_id = result.scalar()

    for sp in data["splits"]:
        await db.execute(
            insert(splits).values(
                guid=str(uuid.uuid4()),
                transaction_id=txn_id,
                account_id=sp["account_id"],
                memo=sp.get("memo", ""),
                value_num=sp["value_num"],
                value_denom=sp["value_denom"],
                quantity_num=sp["value_num"],
                quantity_denom=sp["value_denom"],
                reconcile_state="n",
            )
        )

    await db.commit()
    return txn_id


async def update_transaction(db: AsyncSession, txn_id: int, data: dict) -> None:
    await db.execute(
        update(transactions)
        .where(transactions.c.id == txn_id)
        .values(
            post_date=data["post_date"],
            description=data["description"],
            notes=data.get("notes", ""),
        )
    )
    # Supprimer anciens splits et recréer
    await db.execute(delete(splits).where(splits.c.transaction_id == txn_id))
    for sp in data["splits"]:
        await db.execute(
            insert(splits).values(
                guid=str(uuid.uuid4()),
                transaction_id=txn_id,
                account_id=sp["account_id"],
                memo=sp.get("memo", ""),
                value_num=sp["value_num"],
                value_denom=sp["value_denom"],
                quantity_num=sp["value_num"],
                quantity_denom=sp["value_denom"],
                reconcile_state=sp.get("reconcile_state", "n"),
            )
        )
    await db.commit()


async def delete_transaction(db: AsyncSession, txn_id: int) -> None:
    await db.execute(delete(transactions).where(transactions.c.id == txn_id))
    await db.commit()


async def toggle_reconcile(db: AsyncSession, split_id: int) -> str:
    result = await db.execute(select(splits.c.reconcile_state).where(splits.c.id == split_id))
    current = result.scalar() or "n"
    next_state = {"n": "c", "c": "y", "y": "n"}[current]
    await db.execute(
        update(splits).where(splits.c.id == split_id).values(reconcile_state=next_state)
    )
    await db.commit()
    return next_state


async def get_transaction(db: AsyncSession, txn_id: int) -> dict | None:
    result = await db.execute(
        select(transactions).where(transactions.c.id == txn_id)
    )
    row = result.first()
    if not row:
        return None
    txn = dict(row._mapping)
    sp_result = await db.execute(
        select(splits, accounts.c.name.label("account_name"))
        .join(accounts, splits.c.account_id == accounts.c.id)
        .where(splits.c.transaction_id == txn_id)
    )
    txn["splits"] = [dict(r._mapping) for r in sp_result]
    return txn


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f} €"
