from decimal import Decimal

import pytest

from suzorako.services.validation import (
    ValidationError,
    assert_postable,
    balance_splits,
    validate_account_parent,
)
from tests.conftest import add_account


# --- balance_splits (pur, sans base) ---------------------------------------

def _s(account_id, amount, memo=""):
    return {"account_id": account_id, "amount": amount, "memo": memo}


def test_balance_accepts_balanced_transaction():
    out = balance_splits([_s(1, Decimal("-50")), _s(2, Decimal("50"))])
    assert len(out) == 2
    assert out[0]["value_num"] == -5000 and out[0]["value_denom"] == 100
    assert out[1]["value_num"] == 5000


def test_balance_autofills_single_blank_split():
    out = balance_splits([_s(1, Decimal("-50")), _s(2, None)])
    # La ventilation vide est complétée pour équilibrer : +50.
    assert out[1]["value_num"] == 5000
    assert out[1]["value_denom"] == 100


def test_balance_autofills_blank_across_multiple_known():
    out = balance_splits([_s(1, Decimal("-30")), _s(2, Decimal("-20")), _s(3, None)])
    assert out[2]["value_num"] == 5000  # +50 pour équilibrer -30 -20


def test_balance_rejects_unbalanced():
    with pytest.raises(ValidationError, match="pas équilibrée"):
        balance_splits([_s(1, Decimal("50")), _s(2, Decimal("50"))])


def test_balance_rejects_single_entry():
    with pytest.raises(ValidationError, match="au moins deux"):
        balance_splits([_s(1, Decimal("50"))])


def test_balance_rejects_multiple_blanks():
    with pytest.raises(ValidationError, match="une seule ventilation"):
        balance_splits([_s(1, None), _s(2, None)])


def test_balance_ignores_entries_without_account():
    out = balance_splits([_s(1, Decimal("-50")), _s(2, Decimal("50")), _s(None, Decimal("99"))])
    assert len(out) == 2


def test_balance_tolerates_rounding_noise():
    # Écart d'un dixième de centime : accepté.
    out = balance_splits([_s(1, Decimal("-50.001")), _s(2, Decimal("50"))])
    assert len(out) == 2


# --- validate_account_parent (avec base) -----------------------------------

async def test_parent_same_type_ok(db):
    parent = await add_account(db, "Actifs", "ASSET")
    # Ne lève pas.
    await validate_account_parent(db, account_type="ASSET", parent_id=parent)


async def test_parent_different_type_rejected(db):
    equity = await add_account(db, "Capital", "EQUITY")
    with pytest.raises(ValidationError, match="même type"):
        await validate_account_parent(db, account_type="EXPENSE", parent_id=equity)


async def test_parent_not_found_rejected(db):
    with pytest.raises(ValidationError, match="n'existe pas"):
        await validate_account_parent(db, account_type="ASSET", parent_id=9999)


async def test_parent_none_is_ok(db):
    await validate_account_parent(db, account_type="ASSET", parent_id=None)


async def test_self_parent_rejected(db):
    a = await add_account(db, "Banque", "ASSET")
    with pytest.raises(ValidationError, match="son propre parent"):
        await validate_account_parent(db, account_type="ASSET", parent_id=a, account_id=a)


async def test_cycle_rejected(db):
    parent = await add_account(db, "Actifs", "ASSET")
    child = await add_account(db, "Banque", "ASSET", parent_id=parent)
    # Mettre 'parent' enfant de son propre enfant → cycle.
    with pytest.raises(ValidationError, match="cycle"):
        await validate_account_parent(
            db, account_type="ASSET", parent_id=child, account_id=parent
        )


# --- assert_postable -------------------------------------------------------

async def test_assert_postable_allows_normal_account(db):
    a = await add_account(db, "Banque", "ASSET")
    await assert_postable(db, [a])


async def test_assert_postable_rejects_placeholder(db):
    a = await add_account(db, "Banque", "ASSET")
    grp = await add_account(db, "Regroupement", "ASSET", placeholder=1)
    with pytest.raises(ValidationError, match="regroupement"):
        await assert_postable(db, [a, grp])
