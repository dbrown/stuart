# entry.py
# Entry quality scoring: survival probability, composite score, position sizing.
#
# Public entry points:
#   entry_quality()  — full evaluation, returns sizing + recommendation
#   is_effectively_locked() — score-differential gate for early periods

import math
from scipy.stats import norm

from config import (
    BANKROLL, USE_MAKER, MAX_TRADE,
    MIN_SURVIVAL, MIN_EDGE, MIN_PRICE,
)
from fees import kalshi_fee
from kelly import max_kelly_for_drawdown_constraint


# ── Early-game gate ───────────────────────────────────────────────────────────

def is_effectively_locked(score_diff: int, seconds_remaining: int) -> bool:
    """
    Return True if the current lead is large enough relative to time remaining
    that the game is effectively decided (comeback probability < ~5%).

    Threshold: score_diff ≥ 0.3 pts per total minute remaining.

    Calibration:
        Q2 18:24 clock → 42.4 min total → need +13 pt lead
        Q4  5:00 clock →  5.0 min total → need  +2 pt lead
    """
    if seconds_remaining <= 0:
        return True
    required_lead = (seconds_remaining / 60) * 0.3
    return score_diff >= required_lead


# ── Win-probability helpers ───────────────────────────────────────────────────

def wp_survival_probability(
    p_current:         float,
    p_floor:           float,
    seconds_remaining: int,
    score_diff:        int,   # kept for future score-conditional models
) -> float:
    """
    Probability that WP stays above p_floor for the rest of the game,
    modelled as a Brownian motion with reflection.
    """
    if seconds_remaining <= 0:
        return 1.0 if p_current >= p_floor else 0.0

    tau    = seconds_remaining / 2880
    wp_vol = 0.28 * math.sqrt(tau) * math.sqrt(
        max(0.0, p_current * (1 - p_current) * 4))

    if wp_vol < 1e-6:
        return 1.0 if p_current >= p_floor else 0.0

    z        = (p_current - p_floor) / wp_vol
    survival = norm.cdf(z) - math.exp(-2 * z**2) * norm.cdf(-z)
    return max(0.0, min(1.0, survival))


def wp_volatility_remaining(p_current: float, seconds_remaining: int) -> float:
    """Expected WP volatility for the remaining game time."""
    tau  = seconds_remaining / 2880
    base = p_current * (1 - p_current)
    return round(math.sqrt(max(0.0, base * tau)) * 0.85, 4)


# ── Zero-sizing helper ────────────────────────────────────────────────────────

def _zero_sizing(
    recommendation:   str,
    raw_edge:         float,
    survival:         float,
    vol_remaining:    float,
    velocity:         float,
    score:            float = 0.0,
) -> dict:
    """Return a fully-formed entry dict with zero sizing for any blocked trade."""
    return {
        "valid":            True,
        "score":            score,
        "recommendation":   recommendation,
        "raw_edge":         round(raw_edge, 4),
        "survival":         round(survival, 4),
        "vol_remaining":    vol_remaining,
        "velocity":         round(velocity, 3),
        "f_max":            0.0,
        "f_star":           0.0,
        "kelly_multiplier": 0.0,
        "dollars":          0,
        "contracts":        0,
        "ev":               0,
    }


# ── Main scorer ───────────────────────────────────────────────────────────────

def entry_quality(
    p_current:         float,
    kalshi_ask:        float | int,
    seconds_remaining: int,
    score_diff:        int,
    period:            int,
    bankroll:          float = BANKROLL,
    maker:             bool  = USE_MAKER,
    min_edge:          float = MIN_EDGE,
    min_survival:      float = MIN_SURVIVAL,
) -> dict:
    """
    Evaluate whether to enter a trade.

    Returns a dict with keys:
        valid, score, recommendation,
        raw_edge, survival, vol_remaining, velocity,
        f_max, f_star, kelly_multiplier,
        dollars, contracts, ev

    'contracts' is always 0 when recommendation contains SKIP or WAIT.
    'maybe_trade' treats any SKIP/WAIT recommendation as a hard block.
    """
    price    = kalshi_ask / 100 if kalshi_ask > 1 else float(kalshi_ask)
    fee      = kalshi_fee(1, kalshi_ask, maker=maker)
    net_win  = (1 - price) - fee
    raw_edge = p_current - price

    vol_remaining = wp_volatility_remaining(p_current, seconds_remaining)
    vel_norm      = min(1.0, 3600 / max(seconds_remaining, 60))
    survival      = wp_survival_probability(
        p_current         = p_current,
        p_floor           = price + 0.02,
        seconds_remaining = seconds_remaining,
        score_diff        = score_diff,
    )

    # ── Hard block 1: below target price zone ─────────────────────────
    if price < (MIN_PRICE / 100):
        return _zero_sizing("SKIP — below target zone",
                            raw_edge, survival, vol_remaining, vel_norm)

    # ── Hard block 2: fee exceeds profit ──────────────────────────────
    if net_win <= 0:
        return _zero_sizing("SKIP — fee exceeds profit",
                            raw_edge, survival, vol_remaining, vel_norm)

    # ── Hard block 3: edge at or below minimum ───────────────────────
    if raw_edge <= min_edge:
        return _zero_sizing(
            f"SKIP — edge {raw_edge:+.1%} < {min_edge:.0%} min",
            raw_edge, survival, vol_remaining, vel_norm)

    # ── Period gate: early game requires blowout lead ─────────────────
    if period < 4 and not is_effectively_locked(score_diff, seconds_remaining):
        minutes_remaining = seconds_remaining / 60
        required_lead     = minutes_remaining * 0.3
        return _zero_sizing(
            f"WAIT — Q{period} needs +{required_lead:.0f}pt lead "
            f"(have {score_diff:+d})",
            raw_edge, survival, vol_remaining, vel_norm)

    # ── Full evaluation ───────────────────────────────────────────────
    kelly_c: dict = {
        "valid": False, "f_max": 0.0, "f_star": 0.0,
        "kelly_multiplier": 0.0, "reason": "no edge",
    }
    if net_win > 0 and raw_edge > 0:
        net_loss = price
        b        = net_win / net_loss
        kelly_c  = max_kelly_for_drawdown_constraint(
            p=p_current, b=b, D=0.25, confidence=0.95, n_bets=250)

    # Composite score 0–100
    edge_score     = min(1.0, max(0.0, raw_edge / 0.15))
    survival_score = max(0.0, (survival - min_survival) / (1 - min_survival))
    velocity_score = vel_norm
    kelly_score    = min(1.0, kelly_c["f_max"] / 0.10) if kelly_c["valid"] else 0.0

    score = round(
        (0.30 * edge_score +
         0.40 * survival_score +
         0.20 * velocity_score +
         0.10 * kelly_score) * 100,
        1,
    )

    # Position sizing
    dollars = contracts = ev = 0
    if kelly_c["valid"] and kelly_c["f_max"] > 0:
        raw_dollars = bankroll * kelly_c["f_max"]
        dollars     = round(min(raw_dollars, MAX_TRADE), 2)
        contracts   = max(0, int(dollars / price))
        ev          = round(
            ((p_current * net_win) - ((1 - p_current) * price)) * contracts, 2)

    # Recommendation label
    if score >= 70 and survival >= min_survival:
        rec = "★ STRONG ENTRY"
    elif score >= 50 and survival >= min_survival:
        rec = "ENTER"
    elif survival < min_survival:
        rec = f"WAIT — survival {survival:.0%} < {min_survival:.0%}"
    elif score >= 30:
        rec = "MARGINAL"
    else:
        rec = "SKIP"

    return {
        "valid":            True,
        "score":            score,
        "recommendation":   rec,
        "raw_edge":         round(raw_edge, 4),
        "survival":         round(survival, 4),
        "vol_remaining":    vol_remaining,
        "velocity":         round(vel_norm, 3),
        "f_max":            kelly_c["f_max"],
        "f_star":           kelly_c["f_star"],
        "kelly_multiplier": kelly_c["kelly_multiplier"],
        "dollars":          dollars,
        "contracts":        contracts,
        "ev":               ev,
    }
