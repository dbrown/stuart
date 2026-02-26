# espn.py
# ESPN API interactions.
#
# Two responsibilities:
#   fetch_scoreboard()  — pull today's game list for a league (used by get_espn_games.py)
#   get_live_state()    — pull current score, WP, clock for a specific game_id

import requests
from datetime import datetime

from config import ESPN_HEADERS, ESPN_SCOREBOARD_ENDPOINTS, ESPN_SUMMARY_ENDPOINTS


# ── Scoreboard (game discovery) ───────────────────────────────────────────────

def fetch_scoreboard(league: str) -> list[dict]:
    """
    Fetch today's games from the ESPN scoreboard endpoint for a given league.

    Returns a list of dicts:
        game_id, home_team, away_team, status, date, time
    """
    url = ESPN_SCOREBOARD_ENDPOINTS.get(league)
    if not url:
        raise ValueError(f"Unknown league: {league!r}")

    scoreboard = requests.get(url, headers=ESPN_HEADERS, timeout=10).json()
    today      = datetime.today().strftime("%Y-%m-%d")
    games      = []

    for event in scoreboard.get("events", []):
        abbrev    = event.get("shortName", "?")
        teams     = abbrev.split(" @ ") if " @ " in abbrev else ["?", "?"]
        home_team = teams[1] if len(teams) == 2 else "?"
        away_team = teams[0] if len(teams) == 2 else "?"

        games.append({
            "game_id":   event.get("id", "?"),
            "home_team": home_team,
            "away_team": away_team,
            "status":    event.get("status", {}).get("type", {}).get("name", "?"),
            "date":      today,
            "time":      event.get("date"),  # ISO 8601
        })

    return games


# ── Live game state ───────────────────────────────────────────────────────────

def _parse_seconds_remaining(clock: str, period: int) -> int | None:
    """
    Convert a display clock string + period into total seconds left in the game.
    Handles both 'MM:SS' and decimal (seconds-only) formats.
    """
    try:
        if ":" in clock:
            parts             = clock.split(":")
            clock_seconds     = int(parts[0]) * 60 + int(float(parts[1]))
        else:
            clock_seconds = int(float(clock))

        quarters_left = max(0, 4 - period)
        return clock_seconds + quarters_left * 12 * 60
    except (ValueError, IndexError):
        return None


def get_live_state(game_id: str, league: str = "nba") -> dict:
    """
    Fetch current game state from ESPN summary endpoint.

    Returns a dict with keys:
        game_id, game_state, period, period_str, clock, detail,
        home_wp, away_wp, home_score, away_score,
        seconds_remaining, possession

    game_state is one of: 'pre', 'in', 'post', 'final', 'error'
    """
    endpoint = ESPN_SUMMARY_ENDPOINTS.get(league, ESPN_SUMMARY_ENDPOINTS["nba"])

    try:
        data  = requests.get(
            endpoint, params={"event": game_id},
            headers=ESPN_HEADERS, timeout=5,
        ).json()
    except Exception as e:
        return {"game_id": game_id, "game_state": "error", "error": str(e)}

    try:
        comp      = data.get("header", {}).get("competitions", [{}])[0]
        status    = comp.get("status", {})
        stype     = status.get("type", {})
        state     = stype.get("state", "pre")
        completed = stype.get("completed", False)
        period    = status.get("period", 0)
        clock     = status.get("displayClock", "?")
        detail    = stype.get("shortDetail", "")

        period_str = (
            f"Q{period}"       if 1 <= period <= 4 else
            f"OT{period - 4}"  if period > 4        else
            "PRE"
        )

        if completed or state == "post":
            return {
                "game_id": game_id, "game_state": "final",
                "period_str": "FINAL", "clock": "", "detail": detail,
            }

        if state == "pre":
            return {
                "game_id": game_id, "game_state": "pre",
                "period_str": "PRE", "clock": "", "detail": detail,
                "home_wp": None, "away_wp": None,
                "home_score": None, "away_score": None,
                "possession": None, "seconds_remaining": None,
                "period": 0,
            }

        # Scores and team IDs
        home_score = away_score = None
        home_team_id = away_team_id = None
        for c in comp.get("competitors", []):
            if c.get("homeAway") == "home":
                home_score   = c.get("score", "?")
                home_team_id = c.get("team", {}).get("id")
            else:
                away_score   = c.get("score", "?")
                away_team_id = c.get("team", {}).get("id")

        # Win probability
        home_wp = away_wp = None
        wp_series = data.get("winprobability", [])
        if wp_series:
            last    = wp_series[-1]
            home_wp = round(last["homeWinPercentage"] * 100)
            away_wp = 100 - home_wp

        # Possession
        possession   = None
        situation    = data.get("situation", comp.get("situation", {}))
        poss_team_id = situation.get("possession")
        if poss_team_id:
            if str(poss_team_id) == str(home_team_id):
                possession = "home"
            elif str(poss_team_id) == str(away_team_id):
                possession = "away"

        return {
            "game_id":           game_id,
            "game_state":        state,
            "home_wp":           home_wp,
            "away_wp":           away_wp,
            "home_score":        home_score,
            "away_score":        away_score,
            "period":            period,
            "period_str":        period_str,
            "clock":             clock,
            "seconds_remaining": _parse_seconds_remaining(clock, period),
            "possession":        possession,
            "detail":            detail,
        }

    except Exception as e:
        return {"game_id": game_id, "game_state": "error", "error": str(e)}
