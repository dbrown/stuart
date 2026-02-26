import requests
import json
from datetime import datetime

headers = {"User-Agent": "Mozilla/5.0"}

leagues = {
    'nba': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
    'ncaabbm': 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=357',
    'ncaabbw': 'https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard?groups=50&limit=357',
}

for league, url in leagues.items():
    try:
        scoreboard = requests.get(url, headers=headers, timeout=10).json()
    except Exception as e:
        print(f"Error fetching {league}: {e}")
        continue

    cleaned_games = []
    today = datetime.today().strftime("%Y-%m-%d")
    for event in scoreboard.get("events", []):
        game_id = event.get("id", "?")
        name = event.get("name", "?")
        abbreviation = event.get("shortName", "?")
        teams = abbreviation.split(" @ ") if " @ " in abbreviation else ["?", "?"]
        home_team = teams[1] if len(teams) == 2 else "?"
        away_team = teams[0] if len(teams) == 2 else "?"
        status = event.get("status", {}).get("type", {}).get("name", "?")
        scheduled_time = event.get("date", None)  # ISO8601 string
        cleaned_games.append({
            "game_id": game_id,
            "home_team": home_team,
            "away_team": away_team,
            "status": status,
            "date": today,
            "time": scheduled_time
        })

    filename = f"espn_games_{league}.json"
    with open(filename, "w") as f:
        json.dump(cleaned_games, f, indent=4)
    print(f"Wrote {len(cleaned_games)} games to {filename}")