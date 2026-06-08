from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import accounts, commodities
from suzorako.utils.money import to_decimal

ACCOUNT_TYPES_ORDER = ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]
ACCOUNT_TYPE_LABELS = {
    "ASSET": "Actif",
    "LIABILITY": "Passif",
    "EQUITY": "Capitaux propres",
    "INCOME": "Revenus",
    "EXPENSE": "Dépenses",
}


async def get_all_accounts(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(accounts, commodities.c.mnemonic.label("currency"))
        .outerjoin(commodities, accounts.c.commodity_id == commodities.c.id)
        .where(accounts.c.hidden == 0)
        .order_by(accounts.c.account_type, accounts.c.parent_id.nullsfirst(), accounts.c.name)
    )
    return [dict(r._mapping) for r in result]


async def get_account(db: AsyncSession, account_id: int) -> dict | None:
    result = await db.execute(
        select(accounts, commodities.c.mnemonic.label("currency"))
        .outerjoin(commodities, accounts.c.commodity_id == commodities.c.id)
        .where(accounts.c.id == account_id)
    )
    row = result.first()
    return dict(row._mapping) if row else None


async def get_account_balance(db: AsyncSession, account_id: int) -> Decimal:
    """Solde récursif : somme les splits du compte et de tous ses sous-comptes."""
    result = await db.execute(
        text("""
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM accounts WHERE id = :account_id
                UNION ALL
                SELECT a.id FROM accounts a JOIN subtree s ON a.parent_id = s.id
            )
            SELECT COALESCE(SUM(CAST(s.value_num AS REAL) / s.value_denom), 0)
            FROM splits s
            JOIN subtree t ON s.account_id = t.id
        """),
        {"account_id": account_id},
    )
    value = result.scalar()
    return Decimal(str(value))


async def build_account_tree(db: AsyncSession) -> list[dict]:
    """Retourne la liste des comptes enrichie avec leur solde et leur profondeur."""
    all_accts = await get_all_accounts(db)
    by_id = {a["id"]: a for a in all_accts}

    # Calcul de profondeur (avec garde anti-cycle)
    def depth(acct: dict) -> int:
        d = 0
        current = acct
        seen = {acct["id"]}
        while current["parent_id"] is not None:
            parent = by_id.get(current["parent_id"])
            if parent is None or parent["id"] in seen:
                break
            seen.add(parent["id"])
            d += 1
            current = parent
        return d

    for acct in all_accts:
        acct["depth"] = depth(acct)

    # Grouper par type pour l'affichage
    grouped: dict[str, list] = {t: [] for t in ACCOUNT_TYPES_ORDER}
    for acct in all_accts:
        t = acct["account_type"]
        if t in grouped:
            grouped[t].append(acct)

    return grouped


async def get_all_commodities(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(commodities))
    return [dict(r._mapping) for r in result]


async def create_account(db: AsyncSession, data: dict) -> dict:
    import uuid
    from sqlalchemy import insert
    result = await db.execute(
        insert(accounts).values(
            guid=str(uuid.uuid4()),
            name=data["name"],
            account_type=data["account_type"],
            commodity_id=data.get("commodity_id"),
            parent_id=data.get("parent_id") or None,
            placeholder=data.get("placeholder", 0),
            description=data.get("description", ""),
        ).returning(accounts)
    )
    await db.commit()
    return dict(result.first()._mapping)


async def update_account(db: AsyncSession, account_id: int, data: dict) -> None:
    from sqlalchemy import update
    await db.execute(
        update(accounts)
        .where(accounts.c.id == account_id)
        .values(
            name=data["name"],
            account_type=data["account_type"],
            commodity_id=data.get("commodity_id"),
            parent_id=data.get("parent_id") or None,
            placeholder=data.get("placeholder", 0),
            description=data.get("description", ""),
        )
    )
    await db.commit()


async def delete_account(db: AsyncSession, account_id: int) -> None:
    from sqlalchemy import update
    await db.execute(
        update(accounts).where(accounts.c.id == account_id).values(hidden=1)
    )
    await db.commit()


async def ensure_default_commodity(db: AsyncSession) -> int:
    """Crée EUR si aucune commodity n'existe. Retourne l'id."""
    from sqlalchemy import insert
    result = await db.execute(select(commodities).where(commodities.c.mnemonic == "EUR"))
    row = result.first()
    if row:
        return row.id
    res = await db.execute(
        insert(commodities).values(
            mnemonic="EUR", fullname="Euro", namespace="CURRENCY", fraction=100
        ).returning(commodities.c.id)
    )
    await db.commit()
    return res.scalar()
