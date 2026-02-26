# kalshi_client.py
# Kalshi API interactions: client construction, price queries, order placement.
#
# Order state is tracked in module-level _orders_placed to prevent re-entering
# the same (ticker, side) within a single polling session.

import kalshi_python

from config import (
    KALSHI_HOST, KALSHI_KEY_ID, KALSHI_PEM,
    KALSHI_SERIES, MIN_PRICE, MIN_EDGE, MIN_SURVIVAL,
)
from datetime import datetime


# ── Session state ─────────────────────────────────────────────────────────────

# Persists for the lifetime of the process; reset between sessions by restarting.
_orders_placed: set[tuple[str, str]] = set()


def reset_session() -> None:
    """Clear the in-session order tracker (useful for testing)."""
    _orders_placed.clear()


# ── Client factory ────────────────────────────────────────────────────────────

def get_kalshi_client() -> kalshi_python.KalshiClient:
    config = kalshi_python.Configuration(host=KALSHI_HOST)
    with open(KALSHI_PEM, "r") as f:
        private_key = f.read()
    config.api_key_id      = KALSHI_KEY_ID
    config.private_key_pem = private_key
    return kalshi_python.KalshiClient(config)


# ── Market data ───────────────────────────────────────────────────────────────

def get_yes_no_prices(ticker: str, client) -> dict:
    """
    Return current bid/ask for both YES and NO sides of a market.

    Returns dict with keys: yes_bid, yes_ask, no_bid, no_ask
    On failure returns: {"error": str}
    """
    try:
        m = client.get_market(ticker=ticker).market
        return {
            "yes_bid": m.yes_bid, "yes_ask": m.yes_ask,
            "no_bid":  m.no_bid,  "no_ask":  m.no_ask,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Market discovery ──────────────────────────────────────────────────────────

def get_league_games(client, league: str) -> list[dict]:
    """
    Fetch today's open markets from Kalshi for a given league.

    Returns a list of dicts:
        ticker, date, home_team, away_team

    Deduplicates by (date, frozenset(teams)) — one row per matchup.
    """
    series_ticker = KALSHI_SERIES.get(league)
    if not series_ticker:
        raise ValueError(f"Unknown league: {league!r}")

    api_response = client.get_markets(
        series_ticker=series_ticker, status="open", limit=1000)

    today_str    = datetime.today().strftime("%Y-%m-%d")
    deduped: dict = {}

    for market in api_response.markets:
        ticker = market.ticker
        parts  = ticker.split("-")

        # Parse date from ticker segment e.g. '26FEB25BKNLAC'
        date_segment = parts[1] if len(parts) > 1 else ""
        date_str     = "?"
        try:
            date_str = datetime.strptime(date_segment[:7], "%y%b%d").strftime("%Y-%m-%d")
        except Exception:
            pass

        if date_str != today_str:
            continue

        home_team  = parts[2] if len(parts) > 2 else "?"
        both_teams = date_segment[7:] if len(parts) > 1 else ""
        away_team  = both_teams.replace(home_team, "") if home_team != "?" else "?"

        game_key = (date_str, tuple(sorted([home_team, away_team])))
        if game_key not in deduped:
            deduped[game_key] = {
                "ticker":    ticker,
                "date":      date_str,
                "home_team": home_team,
                "away_team": away_team,
            }

    return list(deduped.values())


# ── Order management ──────────────────────────────────────────────────────────

def get_open_orders(client) -> list:
    """Return all currently resting (unfilled) orders."""
    try:
        response = client.get_orders(status="resting")
        return response.orders or []
    except Exception as e:
        print(f"  Error fetching open orders: {e}")
        return []


def cancel_order(client, order_id: str) -> bool:
    """Cancel a single resting order by ID. Returns True on success."""
    try:
        client.cancel_order(order_id=order_id)
        print(f"  ✓ Cancelled order {order_id}")
        return True
    except Exception as e:
        print(f"  ✗ Cancel failed {order_id}: {e}")
        return False


# ── Order submission ──────────────────────────────────────────────────────────

def _submit_order(
    client,
    ticker:    str,
    side:      str,
    ask_price: int,
    contracts: int,
    dry_run:   bool,
) -> dict:
    """Low-level order placement. Assumes all guards have already passed."""
    order_key = (ticker, side)

    if dry_run:
        print(f"  [DRY RUN] Would place: {side.upper()} {contracts} contracts "
              f"@ {ask_price}¢  ticker={ticker}")
        _orders_placed.add(order_key)
        return {
            "status": "dry_run", "ticker": ticker, "side": side,
            "contracts": contracts, "price": ask_price,
        }

    price_kwarg = "yes_price" if side == "yes" else "no_price"
    try:
        response = client.create_order(
            ticker        = ticker,
            side          = side,
            action        = "buy",
            count         = contracts,
            time_in_force = "fill_or_kill",
            type          = "limit",
            post_only     = True,
            **{price_kwarg: ask_price},
        )
        _orders_placed.add(order_key)
        print(f"  ✓ ORDER PLACED: {side.upper()} {contracts} @ {ask_price}¢  "
              f"ticker={ticker}  response={response}")
        return {
            "status": "placed", "ticker": ticker, "side": side,
            "contracts": contracts, "price": ask_price, "response": response,
        }
    except Exception as e:
        print(f"  ✗ ORDER FAILED: {side.upper()} {contracts} @ {ask_price}¢  "
              f"ticker={ticker}  error={e}")
        return {"status": "failed", "ticker": ticker, "side": side, "error": str(e)}


def maybe_trade(
    client,
    ticker:    str,
    side:      str,
    entry:     dict,
    ask_price: int | float,
    dry_run:   bool = False,
) -> dict | None:
    """
    Gate function: run all safety checks, then submit if everything passes.
    Returns the order result dict, or None if any guard blocks the trade.

    Guards (all must pass):
        1. ask_price >= MIN_PRICE
        2. entry["contracts"] > 0
        3. entry["raw_edge"] >= MIN_EDGE
        4. entry["survival"] >= MIN_SURVIVAL
        5. entry["score"] >= 50
        6. recommendation does not contain SKIP or WAIT
        7. (ticker, side) not already traded this session
    """
    if not isinstance(ask_price, (int, float)) or ask_price < MIN_PRICE:
        print(f"  [BLOCKED] ask {ask_price}¢ below {MIN_PRICE}¢ floor")
        return None
    if entry.get("contracts", 0) <= 0:
        return None
    if entry.get("raw_edge", 0) < MIN_EDGE:
        return None
    if entry.get("survival", 0) < MIN_SURVIVAL:
        return None
    if entry.get("score", 0) < 50:
        return None

    rec = entry.get("recommendation", "")
    if "SKIP" in rec or "WAIT" in rec:
        return None

    if (ticker, side) in _orders_placed:
        return None

    return _submit_order(
        client    = client,
        ticker    = ticker,
        side      = side,
        ask_price = int(ask_price),
        contracts = entry["contracts"],
        dry_run   = dry_run,
    )
