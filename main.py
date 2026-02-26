#!/usr/bin/env python3
# main.py
# Trading loop entry point.
#
# Workflow:
#   1. Run get_espn_games.py and get_kalshi_games.py first to populate JSON files.
#   2. Run this script on a cron / polling interval.
#
# Usage:
#   python main.py            # dry run (default)
#   python main.py --live     # real orders

import argparse
import json
import datetime
import sys

import pandas as pd
import pytz
from dateutil import parser as dateutil_parser

from config import KALSHI_SERIES, DRY_RUN
from kalshi_client import get_kalshi_client
from merge import merge_games
from display import print_and_trade


LEAGUES = list(KALSHI_SERIES.keys())
EASTERN = pytz.timezone("US/Eastern")


def load_json(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def game_time_est(row) -> datetime.datetime:
    """Parse scheduled game time to Eastern; returns max datetime if missing."""
    t = row.get("time")
    if not t:
        return datetime.datetime.max.replace(tzinfo=EASTERN)
    try:
        return dateutil_parser.parse(t).astimezone(EASTERN)
    except Exception:
        return datetime.datetime.max.replace(tzinfo=EASTERN)


def run(dry_run: bool) -> None:
    now_est = datetime.datetime.now(EASTERN)
    client  = get_kalshi_client()

    for league in LEAGUES:
        try:
            espn_games   = load_json(f"espn_games_{league}.json")
            kalshi_games = load_json(f"kalshi_games_{league}.json")
        except FileNotFoundError as e:
            print(f"[{league}] Missing data file: {e}  "
                  f"— run get_espn_games.py and get_kalshi_games.py first.")
            continue

        print(f"\n{'='*60}")
        print(f"League: {league.upper()}  —  "
              f"{len(espn_games)} ESPN games, {len(kalshi_games)} Kalshi markets")
        print(f"{'='*60}")

        merged = merge_games(espn_games, kalshi_games, league)
        if merged.empty:
            print(f"  No matched games for {league}")
            continue

        merged["_game_time"] = merged.apply(game_time_est, axis=1)
        merged = merged.sort_values("_game_time")

        for _, row in merged.iterrows():
            game_time = row.get("_game_time")
            if game_time and now_est < game_time:
                print(
                    f"Game {row['game_id']}: {row['home_team']} vs {row['away_team']}  "
                    f"—  {game_time.strftime('%m/%d - %I:%M %p EST')} (Not started)"
                )
                print("-" * 60)
                print()
                continue

            print_and_trade(row, client, league=league, dry_run=dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description="Kalshi live trading loop")
    ap.add_argument("--live", action="store_true",
                    help="Place real orders (default: dry run)")
    args = ap.parse_args()

    effective_dry_run = not args.live
    if not effective_dry_run:
        confirm = input("⚠️  LIVE MODE — type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Mode: {'DRY RUN' if effective_dry_run else '🔴 LIVE'}")
    run(dry_run=effective_dry_run)


if __name__ == "__main__":
    main()
