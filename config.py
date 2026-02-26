# config.py
# Single source of truth for all constants, credentials, endpoints, and mappings.
# Nothing else in the codebase should hardcode these values.

# ── Risk / sizing ─────────────────────────────────────────────────────────────
BANKROLL     = 288.0
USE_MAKER    = True
MAX_TRADE    = 20.0    # hard cap per trade in dollars
MIN_SURVIVAL = 0.70    # minimum survival probability to trigger trade
MIN_EDGE     = 0.06    # minimum edge as decimal (0.06 = 6%)
MIN_PRICE    = 75      # minimum Kalshi ask in cents — never buy below this

# ── Execution ─────────────────────────────────────────────────────────────────
DRY_RUN = True         # set False to place real orders

# ── Kalshi API ────────────────────────────────────────────────────────────────
KALSHI_HOST   = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_KEY_ID = "d54b907a-4532-4e6c-926b-998d1a82c5ed"
KALSHI_PEM    = "/Users/dbrown/Development/stuart/rusty.pem"

KALSHI_SERIES = {
    "nba":     "KXNBAGAME",
    "ncaabbm": "KXNCAAMBGAME",
    "ncaabbw": "KXNCAAWBGAME",
}

# ── ESPN API ──────────────────────────────────────────────────────────────────
ESPN_HEADERS = {"User-Agent": "Mozilla/5.0"}

ESPN_SCOREBOARD_ENDPOINTS = {
    "nba":     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "ncaabbm": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=357",
    "ncaabbw": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard?groups=50&limit=357",
}

ESPN_SUMMARY_ENDPOINTS = {
    "nba":     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
    "ncaabbm": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary",
    "ncaabbw": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/summary",
}

# ── Team code mappings ────────────────────────────────────────────────────────
# Kalshi ticker codes → ESPN codes.
# Only non-obvious mappings needed — identical codes pass through unchanged.
KALSHI_TO_ESPN = {
    "nba": {
        "BRK": "BKN", "GS": "GSW", "CHO": "CHA", "NO": "NOP",
        "NY": "NYK", "PHO": "PHX", "SA": "SAS",
    },
    "ncaa": {
        "CLT": "CHAR", "L-MD": "LMD", "OMA": "NEOM", "DETM": "DET",
        "CLE": "CLEV", "WGA": "UWGA", "EKU": "EKY", "VAL": "VALP",
        "APSU": "PEAY", "GCU": "GC", "TXAM": "TA&M", "NW": "NU",
        "MORG": "MORG", "SCST": "SCST", "BC": "BC", "WAKE": "WAKE",
        "PROV": "PROV", "AF": "AFA", "SBU": "SBON", "M-OH": "MOH",
        "LUC": "LCHI", "IU": "IND", "PRES": "PRE", "UPST": "UNF",
        "GWEB": "WEBB", "JAX": "JAC", "STMN": "STET", "KC": "UMKC",
        "BOIS": "BSU", "BUF": "BUFF", "EMU": "MOH", "DAY": "LCHI",
        "MD": "MD", "NU": "NW", "YSU": "YSU",
    },
}
