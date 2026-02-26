# teams.py
# Team code normalization between Kalshi tickers and ESPN identifiers.

from config import KALSHI_TO_ESPN


def _league_map(league: str) -> dict:
    """Return the correct sub-map for a given league string."""
    # Use 'nba' for NBA, 'ncaa' for all college basketball leagues
    if league == "nba":
        key = "nba"
    elif league in ("ncaabbm", "ncaabbw"):
        key = "ncaa"
    else:
        key = league
    return KALSHI_TO_ESPN.get(key, {})


def normalize_kalshi_code(code: str, league: str) -> str:
    """
    Translate a Kalshi team code to its ESPN equivalent.
    Unknown codes are returned unchanged (uppercase).
    """
    code = str(code).upper()
    return _league_map(league).get(code, code)


def get_yes_team_from_ticker(ticker: str) -> str:
    """
    Extract the YES-side team code from a Kalshi market ticker.
    e.g. 'KXNBAGAME-26FEB25BKNLAC-BKN' → 'BKN'
    """
    return ticker.split("-")[-1].upper()
