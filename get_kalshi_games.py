#!/usr/bin/env python3
# get_kalshi_games.py
# Fetches today's open Kalshi markets and writes kalshi_games_{league}.json.
# Run this once before the main trading loop.

import json
import sys

from kalshi_client import get_kalshi_client, get_league_games
from config import KALSHI_SERIES

LEAGUES = list(KALSHI_SERIES.keys())  # ["nba", "ncaabbm", "ncaabbw"]


def main():
    client = get_kalshi_client()
    for league in LEAGUES:
        try:
            games    = get_league_games(client, league)
            filename = f"kalshi_games_{league}.json"
            with open(filename, "w") as f:
                json.dump(games, f, indent=4)
            print(f"Wrote {len(games)} games to {filename}")
        except Exception as e:
            print(f"Error fetching {league}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
