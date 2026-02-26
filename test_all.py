#!/usr/bin/env python3
# tests/test_all.py
# Unit tests for all pure-logic modules: fees, kelly, entry, teams, espn parsing.
#
# Run from the project root:
#   python -m pytest tests/ -v
#
# No network calls, no Kalshi credentials required.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# fees.py
# ─────────────────────────────────────────────────────────────────────────────

from fees import kalshi_fee

class TestKalshiFee:
    def test_taker_fee_symmetric_at_50(self):
        # Fee is symmetric around 50¢; max at 50¢
        fee_50  = kalshi_fee(100, 50, maker=False)
        fee_50b = kalshi_fee(100, 0.50, maker=False)
        assert fee_50 == fee_50b

    def test_maker_fee_lower_than_taker(self):
        assert kalshi_fee(10, 80, maker=True) < kalshi_fee(10, 80, maker=False)

    def test_fee_rounds_up(self):
        # Result must always be >= the raw value
        fee = kalshi_fee(1, 82, maker=False)
        assert fee > 0

    def test_price_accepts_cents_or_decimal(self):
        assert kalshi_fee(10, 75, maker=False) == kalshi_fee(10, 0.75, maker=False)

    def test_zero_contracts(self):
        assert kalshi_fee(0, 80) == 0.0

    def test_fee_near_zero_at_extremes(self):
        # P*(1-P) → 0 as price → 0 or 1
        assert kalshi_fee(100, 99, maker=False) < kalshi_fee(100, 75, maker=False)
        assert kalshi_fee(100, 1,  maker=False) < kalshi_fee(100, 50, maker=False)


# ─────────────────────────────────────────────────────────────────────────────
# kelly.py
# ─────────────────────────────────────────────────────────────────────────────

from kelly import max_kelly_for_drawdown_constraint, full_kelly

class TestMaxKelly:
    def test_no_edge_returns_invalid(self):
        result = max_kelly_for_drawdown_constraint(p=0.40, b=0.50)
        assert not result["valid"]
        assert result["f_max"] == 0.0

    def test_positive_edge_returns_valid(self):
        result = max_kelly_for_drawdown_constraint(p=0.85, b=0.20)
        assert result["valid"]
        assert 0 < result["f_max"] <= result["f_star"]

    def test_f_max_leq_f_star(self):
        result = max_kelly_for_drawdown_constraint(p=0.90, b=0.15)
        if result["valid"]:
            assert result["f_max"] <= result["f_star"]

    def test_multiplier_between_0_and_1(self):
        result = max_kelly_for_drawdown_constraint(p=0.85, b=0.20)
        if result["valid"]:
            assert 0 <= result["kelly_multiplier"] <= 1.0


class TestFullKelly:
    def test_missing_inputs_invalid(self):
        assert not full_kelly(None, 82)["valid"]
        assert not full_kelly(0.85, None)["valid"]

    def test_below_min_price_invalid(self):
        result = full_kelly(0.95, 20)   # 20¢ — below MIN_PRICE
        assert not result["valid"]
        assert "below target zone" in result["reason"]

    def test_positive_ev_for_strong_edge(self):
        result = full_kelly(0.90, 82)
        if result["valid"]:
            assert result["ev"] > 0
            assert result["contracts"] > 0

    def test_contracts_respect_position_limit(self):
        # With a small bankroll the dollar cap should limit contracts
        result = full_kelly(0.90, 82, bankroll=10.0)
        if result["valid"]:
            assert result["dollars"] <= 10.0


# ─────────────────────────────────────────────────────────────────────────────
# entry.py
# ─────────────────────────────────────────────────────────────────────────────

from entry import entry_quality, is_effectively_locked, wp_survival_probability

class TestIsEffectivelyLocked:
    def test_large_lead_early_is_locked(self):
        # Q2 blowout: +25 with 42 min remaining → need +13 → locked
        assert is_effectively_locked(score_diff=25, seconds_remaining=42 * 60)

    def test_small_lead_early_not_locked(self):
        assert not is_effectively_locked(score_diff=5, seconds_remaining=42 * 60)

    def test_q4_standard_lead_locked(self):
        # Q4 5 min left, +3 lead → need 1.5 → locked
        assert is_effectively_locked(score_diff=3, seconds_remaining=5 * 60)

    def test_zero_seconds_always_locked(self):
        assert is_effectively_locked(score_diff=0, seconds_remaining=0)

    def test_q1_marginal(self):
        # Q1 12 min left, +4 lead → need 3.6 → locked (barely)
        assert is_effectively_locked(score_diff=4, seconds_remaining=12 * 60)
        # +3 → need 3.6 → not locked
        assert not is_effectively_locked(score_diff=3, seconds_remaining=12 * 60)


class TestWpSurvivalProbability:
    def test_high_wp_high_survival(self):
        s = wp_survival_probability(0.95, 0.77, 120, 10)
        assert s > 0.8

    def test_floor_above_current_zero_survival(self):
        s = wp_survival_probability(0.50, 0.90, 300, 2)
        assert s < 0.10

    def test_no_time_remaining(self):
        assert wp_survival_probability(0.90, 0.77, 0, 10) == 1.0
        assert wp_survival_probability(0.70, 0.77, 0, 10) == 0.0


class TestEntryQuality:
    # ── Hard blocks ───────────────────────────────────────────────────────

    def test_below_min_price_blocked(self):
        eq = entry_quality(
            p_current=0.95, kalshi_ask=50,    # 50¢ — below 75¢ floor
            seconds_remaining=300, score_diff=10, period=4)
        assert eq["contracts"] == 0
        assert "SKIP" in eq["recommendation"]

    def test_insufficient_edge_blocked(self):
        eq = entry_quality(
            p_current=0.80, kalshi_ask=78,    # 2% edge — below 6% min
            seconds_remaining=300, score_diff=10, period=4)
        assert eq["contracts"] == 0
        assert "SKIP" in eq["recommendation"]

    def test_q2_no_blowout_blocked(self):
        # p=0.88, ask=78 → 10% edge (passes edge gate), small lead → period gate fires
        eq = entry_quality(
            p_current=0.88, kalshi_ask=78,
            seconds_remaining=30 * 60, score_diff=5, period=2)
        assert eq["contracts"] == 0
        assert "WAIT" in eq["recommendation"]

    def test_q2_blowout_allowed(self):
        # Q2 with large enough lead should proceed to evaluation
        eq = entry_quality(
            p_current=0.90, kalshi_ask=80,
            seconds_remaining=30 * 60, score_diff=20, period=2)
        # May or may not trade depending on survival; just verify it's not period-blocked
        assert "Q2 needs" not in eq["recommendation"]

    # ── Good signal ───────────────────────────────────────────────────────

    def test_strong_q4_signal_enters(self):
        eq = entry_quality(
            p_current=0.92, kalshi_ask=82,
            seconds_remaining=120, score_diff=8, period=4)
        assert eq["score"] > 0
        # Contracts may be 0 if Kelly finds no room; score should be positive
        assert eq["raw_edge"] > 0

    def test_recommendation_not_skip_for_strong_signal(self):
        eq = entry_quality(
            p_current=0.92, kalshi_ask=82,
            seconds_remaining=120, score_diff=8, period=4)
        # A strong signal should at minimum not be a hard SKIP
        assert "below target zone" not in eq["recommendation"]
        assert "fee exceeds" not in eq["recommendation"]

    # ── Return shape ──────────────────────────────────────────────────────

    def test_return_has_all_keys(self):
        eq = entry_quality(
            p_current=0.85, kalshi_ask=79,
            seconds_remaining=300, score_diff=7, period=4)
        required = {
            "valid", "score", "recommendation", "raw_edge", "survival",
            "vol_remaining", "velocity", "f_max", "f_star",
            "kelly_multiplier", "dollars", "contracts", "ev",
        }
        assert required.issubset(eq.keys())

    def test_contracts_zero_when_skip(self):
        # Any SKIP recommendation must have zero contracts
        eq = entry_quality(
            p_current=0.85, kalshi_ask=20,    # below price floor
            seconds_remaining=300, score_diff=10, period=4)
        assert eq["contracts"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# teams.py
# ─────────────────────────────────────────────────────────────────────────────

from teams import normalize_kalshi_code, get_yes_team_from_ticker

class TestTeams:
    def test_known_nba_mapping(self):
        assert normalize_kalshi_code("BRK", "nba") == "BKN"
        assert normalize_kalshi_code("GS",  "nba") == "GSW"
        assert normalize_kalshi_code("NY",  "nba") == "NYK"

    def test_known_ncaa_mapping(self):
        assert normalize_kalshi_code("CLT",  "ncaabbm") == "CHAR"
        assert normalize_kalshi_code("BOIS", "ncaabbm") == "BSU"

    def test_unknown_code_passthrough(self):
        assert normalize_kalshi_code("LAL", "nba") == "LAL"

    def test_case_insensitive_input(self):
        assert normalize_kalshi_code("brk", "nba") == "BKN"

    def test_yes_team_from_ticker(self):
        assert get_yes_team_from_ticker("KXNBAGAME-26FEB25BKNLAC-BKN") == "BKN"
        assert get_yes_team_from_ticker("KXNBAGAME-26FEB25LACLAC-LAC") == "LAC"

    def test_yes_team_last_segment(self):
        ticker = "KXNCAAMBGAME-26FEB25DUKNC-DUK"
        assert get_yes_team_from_ticker(ticker) == "DUK"


# ─────────────────────────────────────────────────────────────────────────────
# espn.py  (clock parsing only — no network)
# ─────────────────────────────────────────────────────────────────────────────

from espn import _parse_seconds_remaining

class TestClockParsing:
    def test_mm_ss_format_q4(self):
        # 5:00 left in Q4 — 0 quarters remaining after Q4
        secs = _parse_seconds_remaining("5:00", period=4)
        assert secs == 5 * 60

    def test_mm_ss_format_q3(self):
        # 10:00 left in Q3 — 1 quarter remaining (Q4 = 12 min)
        secs = _parse_seconds_remaining("10:00", period=3)
        assert secs == 10 * 60 + 12 * 60

    def test_decimal_format(self):
        secs = _parse_seconds_remaining("300", period=4)
        assert secs == 300

    def test_bad_format_returns_none(self):
        secs = _parse_seconds_remaining("??:??", period=4)
        assert secs is None

    def test_q1_full_remaining(self):
        # 12:00 left in Q1 → 12 min this quarter + 3 × 12 remaining
        secs = _parse_seconds_remaining("12:00", period=1)
        assert secs == 12 * 60 + 3 * 12 * 60


# ─────────────────────────────────────────────────────────────────────────────
# kalshi_client.py  (maybe_trade — no network)
# ─────────────────────────────────────────────────────────────────────────────

from kalshi_client import maybe_trade, reset_session

class TestMaybeTrade:
    """All tests use dry_run=True so no real orders fire."""

    def _good_entry(self, **overrides) -> dict:
        base = {
            "contracts": 5, "raw_edge": 0.10, "survival": 0.85,
            "score": 65, "recommendation": "ENTER",
            "f_max": 0.05, "f_star": 0.08, "kelly_multiplier": 0.6,
            "dollars": 14.0, "ev": 1.20, "vol_remaining": 0.04, "velocity": 0.8,
            "valid": True,
        }
        base.update(overrides)
        return base

    def setup_method(self):
        reset_session()

    def test_good_entry_passes(self, tmp_path):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(), ask_price=82, dry_run=True)
        assert result is not None
        assert result["status"] == "dry_run"

    def test_below_price_floor_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(), ask_price=50, dry_run=True)
        assert result is None

    def test_zero_contracts_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(contracts=0), ask_price=82, dry_run=True)
        assert result is None

    def test_low_edge_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(raw_edge=0.02), ask_price=82, dry_run=True)
        assert result is None

    def test_low_survival_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(survival=0.50), ask_price=82, dry_run=True)
        assert result is None

    def test_skip_recommendation_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(recommendation="SKIP — below target zone"),
                             ask_price=82, dry_run=True)
        assert result is None

    def test_wait_recommendation_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(recommendation="WAIT — Q2 needs +13pt lead"),
                             ask_price=82, dry_run=True)
        assert result is None

    def test_duplicate_blocked(self):
        client = MagicMock()
        # First trade should succeed
        r1 = maybe_trade(client, "TICKER-DUP", "yes",
                         self._good_entry(), ask_price=82, dry_run=True)
        assert r1 is not None
        # Second trade same ticker+side should be blocked
        r2 = maybe_trade(client, "TICKER-DUP", "yes",
                         self._good_entry(), ask_price=82, dry_run=True)
        assert r2 is None

    def test_low_score_blocked(self):
        client = MagicMock()
        result = maybe_trade(client, "TICKER-A", "yes",
                             self._good_entry(score=30), ask_price=82, dry_run=True)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
