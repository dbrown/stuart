# kelly.py
# Kelly criterion and drawdown-constrained position sizing.
#
# Two public entry points:
#   max_kelly_for_drawdown_constraint() — finds the largest fraction f such
#       that the probability of a 25% drawdown stays below 5%.
#   full_kelly() — convenience wrapper that returns contracts + EV given a
#       true probability and a Kalshi ask price.

import math
from scipy.optimize import brentq

from config import BANKROLL, USE_MAKER, MAX_TRADE, MIN_PRICE
from fees import kalshi_fee


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_return_moments(p: float, b: float, f: float) -> tuple[float, float]:
    """
    First two moments of the log-return distribution for a binary bet.
    p: win probability, b: net-win / net-loss ratio, f: fraction wagered.
    """
    q   = 1 - p
    mu  = f * (b * p - q) - (f**2) * (b**2 * p + q) / 2
    var = f**2 * (b**2 * p + q) - (f * (b * p - q))**2
    return mu, var


def _drawdown_prob(p: float, b: float, f: float,
                   D: float = 0.25, n_bets: int = 250) -> float:
    """
    Continuous-time ruin probability approximation:
        P(max_drawdown > D) ≈ exp(-2μD / σ²) × (1 - exp(-n·μ))
    """
    mu, var = _log_return_moments(p, b, f)
    if mu <= 0 or var <= 0:
        return 1.0
    p_ruin  = math.exp(-2 * mu * D / var)
    horizon = 1 - math.exp(-n_bets * mu)
    return p_ruin * horizon


# ── Public API ────────────────────────────────────────────────────────────────

def max_kelly_for_drawdown_constraint(
    p:          float,
    b:          float,
    D:          float = 0.25,
    confidence: float = 0.95,
    n_bets:     int   = 250,
) -> dict:
    """
    Find the largest Kelly fraction f such that P(drawdown > D) < (1 - confidence).

    Returns a dict with keys:
        valid, f_max, f_star, kelly_multiplier, drawdown_prob, reason
    """
    alpha  = 1 - confidence
    f_star = (b * p - (1 - p)) / b

    if f_star <= 0:
        return {
            "valid": False, "reason": "no edge",
            "f_max": 0.0, "f_star": f_star, "kelly_multiplier": 0.0,
        }

    if _drawdown_prob(p, b, f_star, D, n_bets) <= alpha:
        return {
            "valid":            True,
            "f_max":            round(f_star, 4),
            "f_star":           round(f_star, 4),
            "kelly_multiplier": 1.0,
            "drawdown_prob":    round(_drawdown_prob(p, b, f_star, D, n_bets), 4),
            "reason":           "full Kelly satisfies constraint",
        }

    try:
        f_max = brentq(
            lambda f: _drawdown_prob(p, b, f, D, n_bets) - alpha,
            1e-6, f_star, xtol=1e-6,
        )
    except ValueError:
        return {
            "valid": False, "reason": "no solution",
            "f_max": 0.0, "f_star": f_star, "kelly_multiplier": 0.0,
        }

    return {
        "valid":            True,
        "f_max":            round(f_max, 4),
        "f_star":           round(f_star, 4),
        "kelly_multiplier": round(f_max / f_star, 4),
        "drawdown_prob":    round(_drawdown_prob(p, b, f_max, D, n_bets), 4),
        "reason":           "constrained by drawdown limit",
    }


def full_kelly(
    true_probability: float | None,
    kalshi_ask:       float | int | None,
    bankroll:         float = BANKROLL,
    maker:            bool  = USE_MAKER,
) -> dict:
    """
    Convenience wrapper: given ESPN win probability and Kalshi ask price,
    return optimal contracts and expected value.

    Returns a dict with keys:
        valid, reason, f_star, contracts, dollars, ev
    """
    if true_probability is None or kalshi_ask is None:
        return {
            "valid": False, "reason": "missing data",
            "f_star": None, "contracts": 0, "dollars": 0.0, "ev": 0.0,
        }

    price = kalshi_ask / 100 if kalshi_ask > 1 else kalshi_ask

    if price < (MIN_PRICE / 100):
        return {
            "valid": False, "reason": "below target zone",
            "f_star": None, "contracts": 0, "dollars": 0.0, "ev": 0.0,
        }

    fee      = kalshi_fee(1, kalshi_ask, maker=maker)
    net_win  = round((1 - price) - fee, 6)
    net_loss = price

    if net_win <= 0:
        return {
            "valid": False, "reason": "fee exceeds profit",
            "f_star": 0.0, "contracts": 0, "dollars": 0.0, "ev": 0.0,
        }

    p      = true_probability
    q      = 1 - p
    b      = net_win / net_loss
    f_star = (b * p - q) / b

    if f_star <= 0:
        return {
            "valid": False, "reason": "negative edge",
            "f_star": round(f_star, 4), "contracts": 0, "dollars": 0.0, "ev": 0.0,
        }

    dollars   = round(bankroll * f_star, 2)
    contracts = max(0, int(dollars / price))
    ev        = round(((p * net_win) - (q * net_loss)) * contracts, 2)

    return {
        "valid":     True,
        "reason":    "ok",
        "f_star":    round(f_star, 4),
        "contracts": contracts,
        "dollars":   dollars,
        "ev":        ev,
    }
