import kalshi_python
from kalshi_python.models.get_series_response import GetSeriesResponse
from kalshi_python.rest import ApiException
from pprint import pprint
from datetime import datetime

leagues = {
    'nba': 'KXNBAGAME',
    'ncaabbm': 'KXNCAAMBGAME',
    'ncaabbw': 'KXNCAAWBGAME',
}

def get_kalshi_client():
    # Configure the client
    config = kalshi_python.Configuration(
        host = "https://api.elections.kalshi.com/trade-api/v2"
    )

    # For authenticated requests
    # Read private key from file
    with open("/Users/dbrown/Development/nba/rusty.pem", "r") as f:
        private_key = f.read()

    # these are in .env file
    config.api_key_id = "d54b907a-4532-4e6c-926b-998d1a82c5ed"
    config.private_key_pem = private_key

    client = kalshi_python.KalshiClient(config)
    return client

def get_league_games(client, series_ticker):
    api_response = client.get_markets(series_ticker=series_ticker, status='open', limit=1000)
    deduped_games = {}
    for market in api_response.markets:
        ticker = market.ticker
        parts = ticker.split("-")
        date = parts[1][:7] # 26FEB24
        try:
            date_obj = datetime.strptime(date, "%y%b%d")
            date_str = date_obj.strftime("%Y-%m-%d")
        except Exception:
            date_str = "?"
        home_team = parts[2] if len(parts) > 2 else "?"
        both_teams = parts[1][7:] if len(parts) > 1 else ""
        away_team = both_teams.replace(home_team, "") if home_team != "?" else "?"
        # Create a key that is sorted by team and date
        team_key = tuple(sorted([home_team, away_team]))
        game_key = (date_str, team_key)
        # Only keep one entry per matchup/date
        if game_key not in deduped_games:
            deduped_games[game_key] = {
                "ticker": ticker,
                "date": date_str,
                "home_team": home_team,
                "away_team": away_team,
            }
        # remove any items where the date does not match today's date (since some markets are open for multiple days)
    today_str = datetime.today().strftime("%Y-%m-%d")
    deduped_games = {k: v for k, v in deduped_games.items() if v["date"] == today_str}
    return list(deduped_games.values())

c = get_kalshi_client()
import json
for league, series_ticker in leagues.items():
    games = get_league_games(c, series_ticker)
    filename = f"kalshi_games_{league}.json"
    with open(filename, "w") as f:
        json.dump(games, f, indent=4)
    print(f"Wrote {len(games)} games to {filename}")