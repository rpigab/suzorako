from decimal import ROUND_HALF_UP, Decimal


def to_decimal(num: int, denom: int) -> Decimal:
    return Decimal(num) / Decimal(denom)


def from_decimal(d: Decimal, denom: int = 100) -> tuple[int, int]:
    num = int((d * denom).to_integral_value(rounding=ROUND_HALF_UP))
    return num, denom


def format_amount(num: int, denom: int, symbol: str = "€") -> str:
    value = to_decimal(num, denom)
    return f"{value:,.2f} {symbol}"
