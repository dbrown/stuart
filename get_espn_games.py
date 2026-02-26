#!/usr/bin/env python3
# get_espn_games.py
# Fetches today's games from ESPN and writes espn_games_{league}.json.
# Run this once before the main trading loop.

import json
import sys

from espn import fetch_scoreboard
from config import ESPN_SUMMARY_ENDPOINTS   # just to validate league names

LEAGUES = list(ESPN_SUMMARY_ENDPOINTS.keys())  # ["nba", "ncaabbm", "ncaabbw"]


def main():
    from datetime import datetime
    # Always use today's date in YYYYMMDD for ESPN fetch
    today_str = datetime.today().strftime("%Y%m%d")
    for league in LEAGUES:
        try:
            games    = fetch_scoreboard(league, date=today_str)
            filename = f"espn_games_{league}.json"
            with open(filename, "w") as f:
                json.dump(games, f, indent=4)
            print(f"Wrote {len(games)} games to {filename}")
        except Exception as e:
            print(f"Error fetching {league}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
