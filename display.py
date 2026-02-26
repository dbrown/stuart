# display.py
# Terminal output formatting and the per-game trade orchestration loop.
#
# print_and_trade() is the main entry point: given a merged game row,
# it fetches live data, evaluates entries, prints a summary, and fires
# maybe_trade() for each team.

from config import USE_MAKER
from entry import entry_quality
from espn import get_live_state
from fees import kalshi_fee
from kelly import full_kelly
from kalshi_client import get_yes_no_prices, maybe_trade
from teams import get_yes_team_from_ticker, normalize_kalshi_code


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_kelly(k: dict) -> str:
    if not k.get("valid"):
        return f"— ({k.get('reason', '?')})"
    return (
        f"f*={k['f_star']:.1%}  "
        f"${k['dollars']:.0f}  "
        f"{k['contracts']} contracts  "
        f"EV ${k['ev']:.2f}"
    )


def fmt_entry(eq: dict) -> str:
    sizing = (
        f"  f_max={eq['f_max']:.1%} ({eq['kelly_multiplier']:.2f}x Kelly)  "
        f"${eq['dollars']:.0f}  {eq['contracts']} contracts  EV ${eq['ev']:.2f}"
        if eq["f_max"] > 0 else "  no sizing"
    )
    return (
        f"{eq['recommendation']}  "
        f"score={eq['score']}  "
        f"survival={eq['survival']:.0%}  "
        f"vol={eq['vol_remaining']:.3f}  "
        f"edge={eq['raw_edge']:+.2%}"
        f"{sizing}"
    )


# ── Per-game orchestration ────────────────────────────────────────────────────

def _calc_edge(espn_wp: int | None, yes_ask: int | float | None) -> float | None:
    try:
        return round(float(espn_wp) / 100 - float(yes_ask) / 100, 4)
    except (TypeError, ValueError):
        return None


def _fmt_edge(e: float | None) -> str:
    return f"{e:+.2%}" if e is not None else "?"


_NO_DATA_ENTRY = {
    "valid": True, "score": 0, "recommendation": "— no data",
    "raw_edge": 0.0, "survival": 0.0, "vol_remaining": 0.0,
    "velocity": 0.0, "f_max": 0.0, "f_star": 0.0,
    "kelly_multiplier": 0.0, "dollars": 0, "contracts": 0, "ev": 0,
}


def print_and_trade(
    row,           # a pandas Series / dict row from the merged game DataFrame
    client,
    league:  str,
    dry_run: bool = True,
) -> None:
    """
    For one matched game:
      1. Fetch live ESPN state + Kalshi prices.
      2. Evaluate entry quality for home and away sides.
      3. Print a formatted summary.
      4. Call maybe_trade() for each side.
    """
    game_id   = row["game_id"]
    ticker    = row["ticker"]
    home_code = normalize_kalshi_code(row["home_team"], league)
    away_code = normalize_kalshi_code(row["away_team"], league)
    yes_team  = normalize_kalshi_code(get_yes_team_from_ticker(ticker), league)
    yes_is_home = yes_team == home_code

    espn   = get_live_state(game_id, league)
    prices = get_yes_no_prices(ticker, client)

    # Debug line — confirms mapping is correct
    print(
        f"  [DEBUG] raw prices: yes_bid={prices.get('yes_bid')}  "
        f"yes_ask={prices.get('yes_ask')}  "
        f"no_bid={prices.get('no_bid')}  "
        f"no_ask={prices.get('no_ask')}  "
        f"yes_team={yes_team}  yes_is_home={yes_is_home}"
    )

    if espn.get("game_state") == "final":
        print(f"Game {game_id}: FINAL")
        return
    if espn.get("game_state") == "error":
        print(f"Game {game_id}: ERROR — {espn.get('error')}")
        return

    # Map YES/NO sides to home/away
    if yes_is_home:
        home_bid, home_ask = prices.get("yes_bid", "?"), prices.get("yes_ask", "?")
        away_bid, away_ask = prices.get("no_bid",  "?"), prices.get("no_ask",  "?")
        home_side, away_side = "yes", "no"
    else:
        home_bid, home_ask = prices.get("no_bid",  "?"), prices.get("no_ask",  "?")
        away_bid, away_ask = prices.get("yes_bid", "?"), prices.get("yes_ask", "?")
        home_side, away_side = "no", "yes"

    home_espn_wp = espn.get("home_wp")
    away_espn_wp = espn.get("away_wp")
    secs         = espn.get("seconds_remaining")
    period       = espn.get("period", 0)

    home_edge  = _calc_edge(home_espn_wp, home_ask)
    away_edge  = _calc_edge(away_espn_wp, away_ask)
    home_kelly = full_kelly(
        home_espn_wp / 100 if home_espn_wp is not None else None, home_ask)
    away_kelly = full_kelly(
        away_espn_wp / 100 if away_espn_wp is not None else None, away_ask)

    # Pre-game display
    if espn["game_state"] == "pre":
        print(f"Game {game_id}:")
        print(f"  {home_code} vs {away_code}  —  {espn.get('detail', 'Scheduled')}")
        print(f"  {home_code}  ESPN: {home_espn_wp}%  Bid: {home_bid}  "
              f"Ask: {home_ask}  Edge: {_fmt_edge(home_edge)}  "
              f"Kelly: {fmt_kelly(home_kelly)}")
        print(f"  {away_code}  ESPN: {away_espn_wp}%  Bid: {away_bid}  "
              f"Ask: {away_ask}  Edge: {_fmt_edge(away_edge)}  "
              f"Kelly: {fmt_kelly(away_kelly)}")
        print("-" * 60)
        print()
        return

    # In-game display
    home_score = espn.get("home_score", "?")
    away_score = espn.get("away_score", "?")
    clock      = f"{espn['period_str']} {espn['clock']}"
    poss       = espn.get("possession") or "—"

    try:
        home_diff = int(home_score) - int(away_score)
        away_diff = -home_diff
    except (TypeError, ValueError):
        home_diff = away_diff = 0

    def can_compute(wp, ask):
        return wp is not None and secs is not None and isinstance(ask, (int, float))

    home_entry = entry_quality(
        p_current         = home_espn_wp / 100,
        kalshi_ask        = home_ask,
        seconds_remaining = secs or 0,
        score_diff        = home_diff,
        period            = period,
    ) if can_compute(home_espn_wp, home_ask) else _NO_DATA_ENTRY

    away_entry = entry_quality(
        p_current         = away_espn_wp / 100,
        kalshi_ask        = away_ask,
        seconds_remaining = secs or 0,
        score_diff        = away_diff,
        period            = period,
    ) if can_compute(away_espn_wp, away_ask) else _NO_DATA_ENTRY

    print(f"Game {game_id}:")
    print(f"  {home_code}: {home_score} pts  ESPN: {home_espn_wp}%  "
          f"Bid: {home_bid}  Ask: {home_ask}  "
          f"Edge: {_fmt_edge(home_edge)}  Kelly: {fmt_kelly(home_kelly)}")
    print(f"    Entry: {fmt_entry(home_entry)}")
    print(f"  {away_code}: {away_score} pts  ESPN: {away_espn_wp}%  "
          f"Bid: {away_bid}  Ask: {away_ask}  "
          f"Edge: {_fmt_edge(away_edge)}  Kelly: {fmt_kelly(away_kelly)}")
    print(f"    Entry: {fmt_entry(away_entry)}")
    print(f"  Clock: {clock}   Possession: {poss}")

    # Trade execution
    for team_code, entry, side, ask in [
        (home_code, home_entry, home_side, home_ask),
        (away_code, away_entry, away_side, away_ask),
    ]:
        ask_int = int(ask) if isinstance(ask, (int, float)) else 0
        result  = maybe_trade(
            client    = client,
            ticker    = ticker,
            side      = side,
            entry     = entry,
            ask_price = ask_int,
            dry_run   = dry_run,
        )
        if result and result["status"] in ("placed", "dry_run"):
            cost = result["contracts"] * (ask_int / 100)
            tag  = "[DRY RUN] " if dry_run else ""
            print(
                f"  {tag}⚡ TRADE: {team_code}  "
                f"{side.upper()}  {result['contracts']} contracts @ {ask}¢  "
                f"cost ~${cost:.2f}  survival={entry['survival']:.0%}  "
                f"score={entry['score']}"
            )

    print("-" * 60)
    print()
