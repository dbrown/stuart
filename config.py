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
        "SAS": "SA",
        "NOP": "NO",
        "UTA": "UTAH",
        "WAS": "WSH"  
    },
    "ncaa": {
        'AC': 'ACU',  # Abilene Christian
        'ALBY': 'UALB',  # Albany
        'CAMP': 'CAM',  # Campbell
        'CHAT': 'UTC', # Chattanooga
        'CHS': 'CHST', # Charleston Southern
        'COOK': 'BCU',  # Bethune-Cookman
        'CSN': 'CSUN', # Cal State Northridge
        'CSB': 'CSUB', # Cal State Bakersfield
        'HP': 'HPU',  # High Point
        'IW': 'UIW',  # Incarnate Word
        'JAC': 'JAX',  # Jacksonville
        'JVST': 'JXST', # Jacksonville State
        'LMC': 'LEM',
        'LINW': 'LIN',
        'MASSL': 'UML', # Massachusetts Lowell
        'MCNS': 'MCN',
        'MHU': 'MERC', # Mercyhurst
        'MIZZ': 'MIZ', # Missouri
        'MOSU': 'MOST', # missouri state
        'MTU': 'MTSU', # Middle Tennessee
        'MURR': 'MUR', # Murray State
        'NCST': 'NCSU', # North Carolina State
        'NHC': 'NHVN', # New Haven
        'NIAG': 'NIA', # Niagara
        'OKLA': 'OU',  # Oklahoma
        'PRE': 'PRES', # Presbyterian
        'SBON': 'SBU',  # St. Bonaventure
        'SCAR': 'SC',  # South Carolina
        'SCUS': 'UPST',  # USC Upstate
        'SPC': 'SPU',  # Seattle Pacific
        'STNH': 'STO',  # Stonehill,
        'STON': 'STBK',  # Stony Brook
        'TARL': 'TAR',  # Tarleton State
        'TOWS': 'TOW',  # Towson
        'TXAM': 'TA&M',  # Texas A&M
        'UALR': 'LR',  # Arkansas Little Rock
        'UCRV': 'UCR',  # UC Riverside
        'UMKC': 'KC',  # UMKC/Kansas City
        'UST': 'STMN' ,  # St. Thomas Minnesota
        'UTRGV': 'RGV',  # Texas Rio Grande Valley
        'VALP': 'VAL',  # Valparaiso
        'WEBB': 'GWEB',
        'WM': 'W&M'  # William & Mary
    }
}

