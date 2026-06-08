from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_chart_data(db: AsyncSession, year: int, period: str = "monthly") -> dict:
    """Retourne revenus et dépenses par mois pour l'année donnée."""
    result = await db.execute(
        text("""
            SELECT
                strftime('%m', t.post_date) as month,
                a.account_type,
                SUM(CAST(s.value_num AS REAL) / s.value_denom) as total
            FROM splits s
            JOIN transactions t ON s.transaction_id = t.id
            JOIN accounts a ON s.account_id = a.id
            WHERE strftime('%Y', t.post_date) = :year
              AND a.account_type IN ('INCOME', 'EXPENSE')
              AND a.hidden = 0
            GROUP BY month, a.account_type
            ORDER BY month
        """),
        {"year": str(year)},
    )
    rows = result.fetchall()

    months = [str(m).zfill(2) for m in range(1, 13)]
    income = {m: 0.0 for m in months}
    expense = {m: 0.0 for m in months}

    for row in rows:
        m = row[0]
        account_type = row[1]
        total = float(row[2] or 0)
        if account_type == "INCOME":
            income[m] = abs(total)
        elif account_type == "EXPENSE":
            expense[m] = abs(total)

    return {
        "year": year,
        "months": months,
        "income": [income[m] for m in months],
        "expense": [expense[m] for m in months],
    }


async def get_budget_table(db: AsyncSession, year: int) -> list[dict]:
    """Retourne les totaux mensuels par compte INCOME/EXPENSE pour l'année."""
    result = await db.execute(
        text("""
            SELECT
                a.id,
                a.name,
                a.account_type,
                strftime('%m', t.post_date) as month,
                SUM(CAST(s.value_num AS REAL) / s.value_denom) as total
            FROM splits s
            JOIN transactions t ON s.transaction_id = t.id
            JOIN accounts a ON s.account_id = a.id
            WHERE strftime('%Y', t.post_date) = :year
              AND a.account_type IN ('INCOME', 'EXPENSE')
              AND a.hidden = 0
            GROUP BY a.id, month
            ORDER BY a.account_type, a.name, month
        """),
        {"year": str(year)},
    )
    rows = result.fetchall()

    # Pivot : {account_id: {name, type, months: {01..12: total}}}
    accounts: dict = {}
    for row in rows:
        aid = row[0]
        if aid not in accounts:
            accounts[aid] = {
                "id": aid,
                "name": row[1],
                "account_type": row[2],
                "months": {str(m).zfill(2): 0.0 for m in range(1, 13)},
                "annual_total": 0.0,
            }
        accounts[aid]["months"][row[3]] = abs(float(row[4] or 0))
        accounts[aid]["annual_total"] += abs(float(row[4] or 0))

    return list(accounts.values())
