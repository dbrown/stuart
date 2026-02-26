# fees.py
# Kalshi fee calculation.
# Isolated here so it can be unit-tested independently of everything else.
#
# Formula (from Kalshi docs):
#   taker fee = roundup(0.07  × C × P × (1 - P))
#   maker fee = roundup(0.0175 × C × P × (1 - P))
#
# P is expressed as a decimal (0–1), C is contract count.

from decimal import Decimal, ROUND_CEILING


_TAKER_RATE = Decimal("0.07")
_MAKER_RATE = Decimal("0.0175")


def kalshi_fee(contracts: int, price: float | int, maker: bool = False) -> float:
    """
    Return total fee in dollars for a batch of contracts.

    Args:
        contracts: Number of contracts.
        price:     Price in cents (e.g. 82) OR as a decimal (e.g. 0.82).
        maker:     True for maker (post-only) orders, False for taker.

    Returns:
        Fee in dollars, rounded up to the nearest cent.
    """
    rate = _MAKER_RATE if maker else _TAKER_RATE
    c    = Decimal(str(contracts))
    p    = Decimal(str(price / 100 if price > 1 else price))
    raw  = rate * c * p * (1 - p)
    return float(raw.quantize(Decimal("0.01"), rounding=ROUND_CEILING))
