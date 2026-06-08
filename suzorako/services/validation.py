"""Validation métier : invariants de la comptabilité en partie double.

Ce module garantit que les écritures respectent les règles fondamentales :
- une transaction est équilibrée (somme des ventilations = 0) ;
- un sous-compte a le même type que son parent ;
- l'arbre des comptes reste acyclique ;
- on ne poste pas directement sur un compte de regroupement (placeholder).
"""

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from suzorako.database import accounts
from suzorako.services.account_service import ACCOUNT_TYPE_LABELS
from suzorako.utils.money import from_decimal, to_decimal

# Tolérance d'arrondi : une demi-unité au centime près.
BALANCE_TOLERANCE = Decimal("0.005")


class ValidationError(Exception):
    """Erreur de validation présentable à l'utilisateur."""


async def get_descendant_ids(db: AsyncSession, account_id: int) -> set[int]:
    """Renvoie l'id du compte et de tous ses descendants (sous-arbre)."""
    result = await db.execute(
        text("""
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM accounts WHERE id = :account_id
                UNION ALL
                SELECT a.id FROM accounts a JOIN subtree s ON a.parent_id = s.id
            )
            SELECT id FROM subtree
        """),
        {"account_id": account_id},
    )
    return {r[0] for r in result}


async def validate_account_parent(
    db: AsyncSession,
    *,
    account_type: str,
    parent_id: int | None,
    account_id: int | None = None,
) -> None:
    """Vérifie qu'un compte peut être rattaché au parent donné.

    Règles : le parent existe, partage le même type, et le rattachement
    ne crée pas de cycle (parent ≠ soi-même et ∉ descendants).
    """
    if not parent_id:
        return

    parent = (
        await db.execute(
            select(accounts.c.id, accounts.c.account_type).where(accounts.c.id == parent_id)
        )
    ).first()
    if parent is None:
        raise ValidationError("Le compte parent sélectionné n'existe pas.")

    if parent.account_type != account_type:
        raise ValidationError(
            f"Un sous-compte doit être du même type que son parent. "
            f"Parent : {ACCOUNT_TYPE_LABELS.get(parent.account_type, parent.account_type)}, "
            f"compte : {ACCOUNT_TYPE_LABELS.get(account_type, account_type)}."
        )

    if account_id is not None:
        if parent_id == account_id:
            raise ValidationError("Un compte ne peut pas être son propre parent.")
        if parent_id in await get_descendant_ids(db, account_id):
            raise ValidationError(
                "Le compte parent ne peut pas être l'un de ses propres sous-comptes (cycle interdit)."
            )


async def assert_postable(db: AsyncSession, account_ids: list[int]) -> None:
    """Refuse la saisie directe sur un compte de regroupement (placeholder)."""
    if not account_ids:
        return
    rows = (
        await db.execute(
            select(accounts.c.name, accounts.c.placeholder).where(
                accounts.c.id.in_(set(account_ids))
            )
        )
    ).all()
    for name, placeholder in rows:
        if placeholder:
            raise ValidationError(
                f"Le compte « {name} » est un compte de regroupement : "
                f"il ne peut pas recevoir de saisie directe."
            )


def balance_splits(raw_splits: list[dict]) -> list[dict]:
    """Valide et équilibre les ventilations d'une transaction.

    Entrée : liste de dicts ``{account_id: int|None, amount: Decimal|None, memo: str}``.

    - ignore les lignes sans compte ;
    - si exactly une ligne a un montant vide, elle est calculée pour équilibrer
      (équilibrage automatique façon GnuCash) ;
    - exige au moins deux ventilations et une somme nulle (à la tolérance près).

    Sortie : liste de dicts ``{account_id, value_num, value_denom, memo}``.
    Lève ``ValidationError`` si l'écriture est invalide.
    """
    entries = [s for s in raw_splits if s.get("account_id")]
    if len(entries) < 2:
        raise ValidationError(
            "Une transaction doit comporter au moins deux ventilations avec un compte."
        )

    missing = [s for s in entries if s.get("amount") is None]
    if len(missing) > 1:
        raise ValidationError(
            "Renseignez les montants : une seule ventilation peut rester vide "
            "(elle sera équilibrée automatiquement)."
        )

    known_sum = sum((s["amount"] for s in entries if s.get("amount") is not None), Decimal("0"))
    if len(missing) == 1:
        missing[0]["amount"] = -known_sum

    total = sum((s["amount"] for s in entries), Decimal("0"))
    if abs(total) > BALANCE_TOLERANCE:
        raise ValidationError(
            f"La transaction n'est pas équilibrée (écart de {total:+.2f} €). "
            f"La somme des ventilations doit être nulle."
        )

    out = []
    for s in entries:
        num, denom = from_decimal(s["amount"])
        out.append(
            {
                "account_id": s["account_id"],
                "value_num": num,
                "value_denom": denom,
                "memo": s.get("memo", ""),
            }
        )
    return out
