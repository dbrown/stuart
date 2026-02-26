# merge.py
# Joins ESPN and Kalshi game lists into a single DataFrame.
#
# The tricky part: Kalshi tickers encode the YES-team as the "home" team,
# which may not match ESPN's home/away assignment. The frozenset key approach
# handles swaps gracefully.

import pandas as pd

from teams import normalize_kalshi_code


def merge_games(
    espn_games:   list[dict],
    kalshi_games: list[dict],
    league:       str,
) -> pd.DataFrame:
    """
    Match ESPN games to Kalshi markets by (date, frozenset({home, away})).

    Normalizes Kalshi team codes to ESPN codes before matching.
    Logs unmatched games to stdout.

    Returns a DataFrame with columns from both sources.
    Unmatched games are silently dropped (logged but not raised).
    """
    # Normalize Kalshi codes to ESPN equivalents
    for g in kalshi_games:
        g["home_team"] = normalize_kalshi_code(g["home_team"], league)
        g["away_team"] = normalize_kalshi_code(g["away_team"], league)

    # Build a lookup: (date, frozenset(teams)) → kalshi row
    kalshi_lookup: dict = {}
    for g in kalshi_games:
        key = (g["date"], frozenset([g["home_team"], g["away_team"]]))
        kalshi_lookup[key] = g

    merged_rows = []
    for espn_row in espn_games:
        key        = (espn_row["date"],
                      frozenset([espn_row["home_team"], espn_row["away_team"]]))
        kalshi_row = kalshi_lookup.get(key)

        if kalshi_row is None:
            print(f"  [NO MATCH] {espn_row['home_team']} vs "
                  f"{espn_row['away_team']} on {espn_row['date']}")
            continue

        # If Kalshi home/away is swapped relative to ESPN, align to ESPN
        if (espn_row["home_team"] != kalshi_row["home_team"] or
                espn_row["away_team"] != kalshi_row["away_team"]):
            kalshi_row = dict(kalshi_row)
            kalshi_row["home_team"], kalshi_row["away_team"] = (
                kalshi_row["away_team"], kalshi_row["home_team"])

        merged_rows.append({**espn_row, **kalshi_row})

    if not merged_rows:
        return pd.DataFrame()

    return pd.DataFrame(merged_rows)
