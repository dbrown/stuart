import inspect
import requests
import pandas
import kalshi_python
import math
import datetime
import pytz
from dateutil import parser
from decimal import Decimal, ROUND_CEILING
from scipy.stats import norm
from scipy.optimize import brentq

HEADERS = {"User-Agent": "Mozilla/5.0"}
ESPN_SUMMARY_ENDPOINTS = {
    "nba":     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
    "ncaabbm": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary",
    "ncaabbw": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/summary",
}

kalshi_to_espn = {
    "nba": {
        "BRK": "BKN", "GS": "GSW", "CHO": "CHA", "NO": "NOP", "NY": "NYK", "PHO": "PHX", "SA": "SAS"
    },
    "ncaa": {
        "CLT": "CHAR", "L-MD": "LMD", "OMA": "NEOM", "DETM": "DET", "CLE": "CLEV", "WGA": "UWGA", "EKU": "EKY",
        "VAL": "VALP", "APSU": "PEAY", "GCU": "GC", "TXAM": "TA&M", "NW": "NU",
        "MORG": "MORG", "SCST": "SCST", "BC": "BC", "WAKE": "WAKE", "PROV": "PROV",
        "AF": "AFA", "SBU": "SBON", "M-OH": "MOH", "LUC": "LCHI", "IU": "IND", "PRES": "PRE", "UPST": "UNF",
        "GWEB": "WEBB", "JAX": "JAC", "STMN": "STET", "KC": "UMKC", "BOIS": "BSU",
        "BUF": "BUFF", "EMU": "MOH", "DAY": "LCHI", "MD": "MD", "NU": "NW", "YSU": "YSU",
    }
}

BANKROLL      = 288.0
USE_MAKER     = True
MAX_TRADE     = 5.0      # hard cap per trade in dollars
MIN_SURVIVAL  = 0.70      # trigger threshold for live trading
MIN_EDGE      = 0.06      # minimum edge to consider any trade


# ── Team codes ────────────────────────────────────────────────────────────────

def get_team_code(display_name: str, league: str = "nba") -> str:
    if not display_name:
        print(f"ERROR: Missing team code for blank display_name (league={league})")
        import sys; sys.exit(1)
    display_name = display_name.upper()
    map_league   = "nba" if league == "nba" else "ncaa"
    league_map   = kalshi_to_espn.get(map_league, {})
    return league_map.get(display_name, display_name)


def normalize_team_code(code, league):
    code       = str(code).upper()
    map_league = "nba" if league == "nba" else "ncaa"
    league_map = kalshi_to_espn.get(map_league, {})
    return league_map.get(code, code)


# ── Fees ──────────────────────────────────────────────────────────────────────

def kalshi_fee(contracts: int, price: float, maker: bool = False) -> float:
    rate = Decimal("0.0175") if maker else Decimal("0.07")
    c_   = Decimal(str(contracts))
    p    = Decimal(str(price / 100 if price > 1 else price))
    raw  = rate * c_ * p * (1 - p)
    return float(raw.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


# ── Kelly ─────────────────────────────────────────────────────────────────────

def log_return_moments(p: float, b: float, f: float) -> tuple:
    q   = 1 - p
    mu  = f * (b * p - q) - (f**2) * (b**2 * p + q) / 2
    var = f**2 * (b**2 * p + q) - (f * (b * p - q))**2
    return mu, var


def max_kelly_for_drawdown_constraint(
    p:          float,
    b:          float,
    D:          float = 0.25,
    confidence: float = 0.95,
    n_bets:     int   = 250,
) -> dict:
    alpha  = 1 - confidence
    f_star = (b * p - (1 - p)) / b

    if f_star <= 0:
        return {"valid": False, "reason": "no edge", "f_max": 0.0,
                "f_star": f_star, "kelly_multiplier": 0.0}

    def drawdown_prob(f):
        mu, var = log_return_moments(p, b, f)
        if mu <= 0 or var <= 0:
            return 1.0
        p_ruin  = math.exp(-2 * mu * D / var)
        horizon = 1 - math.exp(-n_bets * mu)
        return p_ruin * horizon

    if drawdown_prob(f_star) <= alpha:
        return {
            "valid":            True,
            "f_max":            round(f_star, 4),
            "f_star":           round(f_star, 4),
            "kelly_multiplier": 1.0,
            "drawdown_prob":    round(drawdown_prob(f_star), 4),
            "reason":           "full Kelly satisfies constraint",
        }

    try:
        f_max = brentq(lambda f: drawdown_prob(f) - alpha, 1e-6, f_star, xtol=1e-6)
    except ValueError:
        return {"valid": False, "reason": "no solution", "f_max": 0.0,
                "f_star": f_star, "kelly_multiplier": 0.0}

    return {
        "valid":            True,
        "f_max":            round(f_max, 4),
        "f_star":           round(f_star, 4),
        "kelly_multiplier": round(f_max / f_star, 4),
        "drawdown_prob":    round(drawdown_prob(f_max), 4),
        "reason":           "constrained by drawdown limit",
    }


def full_kelly(
    true_probability: float,
    kalshi_ask:       float,
    bankroll:         float = BANKROLL,
    maker:            bool  = USE_MAKER,
) -> dict:
    if true_probability is None or kalshi_ask is None:
        return {"valid": False, "reason": "missing data",
                "f_star": None, "contracts": 0, "dollars": 0.0, "ev": 0.0}

    price = kalshi_ask / 100 if kalshi_ask > 1 else kalshi_ask
    if price < 0.75:
        return {"valid": False, "reason": "below target zone",
                "f_star": None, "contracts": 0, "dollars": 0.0, "ev": 0.0}

    fee      = kalshi_fee(1, kalshi_ask, maker=maker)
    net_win  = round((1 - price) - fee, 6)
    net_loss = price

    if net_win <= 0:
        return {"valid": False, "reason": "fee exceeds profit",
                "f_star": 0.0, "contracts": 0, "dollars": 0.0, "ev": 0.0}

    p      = true_probability
    q      = 1 - p
    b      = net_win / net_loss
    f_star = (b * p - q) / b

    if f_star <= 0:
        return {"valid": False, "reason": "negative edge",
                "f_star": round(f_star, 4), "contracts": 0, "dollars": 0.0, "ev": 0.0}

    dollars   = round(bankroll * f_star, 2)
    contracts = max(0, int(dollars / price))
    ev        = round(((p * net_win) - (q * net_loss)) * contracts, 2)

    return {
        "valid":     True,
        "reason":    "ok",
        "f_star":    round(f_star, 4),
        "contracts": contracts,
        "dollars":   dollars,
        "ev":        ev,
    }


# ── Entry quality ─────────────────────────────────────────────────────────────

def wp_survival_probability(
    p_current:         float,
    p_floor:           float,
    seconds_remaining: int,
    score_diff:        int,
) -> float:
    if seconds_remaining <= 0:
        return 1.0 if p_current >= p_floor else 0.0
    tau    = seconds_remaining / 2880
    wp_vol = 0.28 * math.sqrt(tau) * math.sqrt(max(0.0, p_current * (1 - p_current) * 4))
    if wp_vol < 1e-6:
        return 1.0 if p_current >= p_floor else 0.0
    z        = (p_current - p_floor) / wp_vol
    survival = norm.cdf(z) - math.exp(-2 * z**2) * norm.cdf(-z)
    return max(0.0, min(1.0, survival))


def wp_volatility_remaining(p_current: float, seconds_remaining: int) -> float:
    tau  = seconds_remaining / 2880
    base = p_current * (1 - p_current)
    return round(math.sqrt(max(0.0, base * tau)) * 0.85, 4)


def entry_quality(
    p_current:         float,
    kalshi_ask:        float,
    seconds_remaining: int,
    score_diff:        int,
    period:            int,
    bankroll:          float = BANKROLL,
    maker:             bool  = USE_MAKER,
    min_edge:          float = MIN_EDGE,
    min_survival:      float = MIN_SURVIVAL,
) -> dict:
    price         = kalshi_ask / 100 if kalshi_ask > 1 else kalshi_ask
    fee           = kalshi_fee(1, kalshi_ask, maker=maker)
    net_win       = (1 - price) - fee
    net_loss      = price
    raw_edge      = p_current - price
    vol_remaining = wp_volatility_remaining(p_current, seconds_remaining)
    vel_norm      = min(1.0, 3600 / max(seconds_remaining, 60))

    # ── Period gate — time-aware, not period-aware ────────────────────
    # Allow entry in any period if the lead is large enough to be
    # effectively locked. Otherwise require Q4.
    minutes_remaining = seconds_remaining / 60
    required_lead     = minutes_remaining * 0.3   # empirical NBA/NCAAB calibration
    effectively_locked = score_diff >= required_lead

    if period < 4 and not effectively_locked:
        return {
            "valid":            True,
            "score":            0,
            "recommendation":   (
                f"WAIT — Q{period} needs +{required_lead:.0f}pt lead "
                f"(have {score_diff:+d})"
            ),
            "raw_edge":         round(raw_edge, 4),
            "survival":         round(wp_survival_probability(
                                    p_current, price + 0.02,
                                    seconds_remaining, score_diff), 4),
            "vol_remaining":    vol_remaining,
            "velocity":         round(vel_norm, 3),
            "f_max":            0.0,
            "f_star":           0.0,
            "kelly_multiplier": 0.0,
            "dollars":          0,
            "contracts":        0,
            "ev":               0,
        }

    # ── Full evaluation ───────────────────────────────────────────────
    survival = wp_survival_probability(
        p_current         = p_current,
        p_floor           = price + 0.02,
        seconds_remaining = seconds_remaining,
        score_diff        = score_diff,
    )

    kelly_c = {"valid": False, "f_max": 0.0, "f_star": 0.0,
               "kelly_multiplier": 0.0, "reason": "no edge"}
    if net_win > 0 and raw_edge > 0:
        b       = net_win / net_loss
        kelly_c = max_kelly_for_drawdown_constraint(
            p=p_current, b=b, D=0.25, confidence=0.95, n_bets=250)

    edge_score     = min(1.0, max(0.0, raw_edge / 0.15))
    survival_score = max(0.0, (survival - min_survival) / (1 - min_survival))
    velocity_score = vel_norm
    kelly_score    = min(1.0, kelly_c["f_max"] / 0.10) if kelly_c["valid"] else 0.0

    composite = (
        0.30 * edge_score     +
        0.40 * survival_score +
        0.20 * velocity_score +
        0.10 * kelly_score
    )
    score = round(composite * 100, 1)

    dollars = contracts = ev = 0
    if kelly_c["valid"] and kelly_c["f_max"] > 0:
        raw_dollars = bankroll * kelly_c["f_max"]
        dollars     = round(min(raw_dollars, MAX_TRADE), 2)
        contracts   = max(0, int(dollars / price))
        ev          = round(((p_current * net_win) -
                             ((1 - p_current) * net_loss)) * contracts, 2)

    if net_win <= 0:
        rec = "SKIP — fee exceeds profit"
    elif price < 0.75:
        rec = "SKIP — below target zone"
    elif raw_edge < min_edge:
        rec = f"SKIP — edge {raw_edge:+.1%} < {min_edge:.0%} min"
    elif score >= 70 and survival >= min_survival:
        rec = "★ STRONG ENTRY"
    elif score >= 50 and survival >= min_survival:
        rec = "ENTER"
    elif survival < min_survival:
        rec = f"WAIT — survival {survival:.0%} < {min_survival:.0%}"
    elif score >= 30:
        rec = "MARGINAL"
    else:
        rec = "SKIP"

    return {
        "valid":            True,
        "score":            score,
        "recommendation":   rec,
        "raw_edge":         round(raw_edge, 4),
        "survival":         round(survival, 4),
        "vol_remaining":    vol_remaining,
        "velocity":         round(vel_norm, 3),
        "f_max":            kelly_c["f_max"],
        "f_star":           kelly_c["f_star"],
        "kelly_multiplier": kelly_c["kelly_multiplier"],
        "dollars":          dollars,
        "contracts":        contracts,
        "ev":               ev,
    }


# ── Kalshi client ─────────────────────────────────────────────────────────────

def get_kalshi_client():
    config = kalshi_python.Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2")
    with open("/Users/dbrown/Development/nba/rusty.pem", "r") as f:
        private_key = f.read()
    config.api_key_id      = "d54b907a-4532-4e6c-926b-998d1a82c5ed"
    config.private_key_pem = private_key
    return kalshi_python.KalshiClient(config)


def get_yes_team_from_ticker(ticker: str) -> str:
    return ticker.split("-")[-1].upper()


def get_kalshi_prices(ticker: str, client) -> dict:
    try:
        m = client.get_market(ticker=ticker).market
        return {"yes_bid": m.yes_bid, "yes_ask": m.yes_ask,
                "no_bid":  m.no_bid,  "no_ask":  m.no_ask}
    except Exception as e:
        return {"error": str(e)}


# ── Order submission ──────────────────────────────────────────────────────────

# Track orders placed this session to avoid re-entering same game
_orders_placed = set()   # set of (ticker, side) tuples


def submit_order(
    client,
    ticker:    str,
    side:      str,   # "yes" or "no"
    ask_price: int,   # cents
    contracts: int,
    dry_run:   bool = False,
) -> dict:
    """
    Place a limit order on Kalshi.

    side      : "yes" buys the YES contract, "no" buys the NO contract
    ask_price : the current ask in cents — used as our limit price
    contracts : number of contracts from Kelly sizing (already capped at MAX_TRADE)
    dry_run   : if True, log the order but do not submit to the exchange

    Uses post_only=True (maker order) and fill_or_kill to avoid partial fills.
    Returns a result dict with status and any exchange response.
    """
    order_key = (ticker, side)

    if order_key in _orders_placed:
        return {"status": "skipped", "reason": "already traded this session",
                "ticker": ticker, "side": side}

    if contracts <= 0:
        return {"status": "skipped", "reason": "0 contracts",
                "ticker": ticker, "side": side}

    if dry_run:
        print(f"  [DRY RUN] Would place: {side.upper()} {contracts} contracts "
              f"@ {ask_price}¢  ticker={ticker}")
        _orders_placed.add(order_key)
        return {"status": "dry_run", "ticker": ticker, "side": side,
                "contracts": contracts, "price": ask_price}

    try:
        # Map side → Kalshi API parameters
        if side == "yes":
            order_params = dict(
                ticker       = ticker,
                side         = "yes",
                action       = "buy",
                count        = contracts,
                yes_price    = ask_price,
                time_in_force= "fill_or_kill",
                type         = "limit",
                post_only    = True,
            )
        else:
            # Buying NO at no_price = ask_price
            order_params = dict(
                ticker       = ticker,
                side         = "no",
                action       = "buy",
                count        = contracts,
                no_price     = ask_price,
                time_in_force= "fill_or_kill",
                type         = "limit",
                post_only    = True,
            )

        response = client.create_order(**order_params)
        _orders_placed.add(order_key)

        print(f"  ✓ ORDER PLACED: {side.upper()} {contracts} @ {ask_price}¢  "
              f"ticker={ticker}  response={response}")
        return {"status": "placed", "ticker": ticker, "side": side,
                "contracts": contracts, "price": ask_price, "response": response}

    except Exception as e:
        print(f"  ✗ ORDER FAILED: {side.upper()} {contracts} @ {ask_price}¢  "
              f"ticker={ticker}  error={e}")
        return {"status": "failed", "ticker": ticker, "side": side, "error": str(e)}


def maybe_trade(
    client,
    ticker:     str,
    side:       str,   # "yes" or "no"
    entry:      dict,  # result from entry_quality()
    ask_price:  int,   # cents
    dry_run:    bool = False,
) -> dict | None:
    """
    Evaluate entry signal and submit order if conditions are met.

    Trading trigger requires ALL of:
      1. survival >= MIN_SURVIVAL (70%)
      2. edge >= MIN_EDGE (6%)
      3. score >= 50 (ENTER or better)
      4. contracts > 0 (Kelly sizing produced a valid position)
      5. ticker+side not already traded this session
    """
    if entry["survival"] < MIN_SURVIVAL:
        return None
    if entry["raw_edge"] < MIN_EDGE:
        return None
    if entry["score"] < 50:
        return None
    if entry["contracts"] <= 0:
        return None
    if (ticker, side) in _orders_placed:
        return None

    return submit_order(
        client    = client,
        ticker    = ticker,
        side      = side,
        ask_price = ask_price,
        contracts = entry["contracts"],
        dry_run   = dry_run,
    )


# ── ESPN ──────────────────────────────────────────────────────────────────────

def get_live_state(game_id: str, league: str = "nba") -> dict:
    try:
        endpoint = ESPN_SUMMARY_ENDPOINTS.get(league, ESPN_SUMMARY_ENDPOINTS["nba"])
        data     = requests.get(endpoint, params={"event": game_id},
                                headers=HEADERS, timeout=5).json()
        comp     = data.get("header", {}).get("competitions", [{}])[0]
        status   = comp.get("status", {})
        stype    = status.get("type", {})
        state    = stype.get("state", "pre")
        completed  = stype.get("completed", False)
        period     = status.get("period", 0)
        clock      = status.get("displayClock", "?")
        detail     = stype.get("shortDetail", "")
        period_str = (f"Q{period}" if 1 <= period <= 4
                      else f"OT{period - 4}" if period > 4 else "PRE")

        if completed or state == "post":
            return {"game_id": game_id, "game_state": "final",
                    "period_str": "FINAL", "clock": "", "detail": detail}

        if state == "pre":
            return {"game_id": game_id, "game_state": "pre",
                    "period_str": "PRE", "clock": "", "detail": detail,
                    "home_wp": None, "away_wp": None, "home_score": None,
                    "away_score": None, "possession": None,
                    "seconds_remaining": None, "period": 0}

        home_score = away_score = None
        home_team_id = away_team_id = None
        for c in comp.get("competitors", []):
            if c.get("homeAway") == "home":
                home_score   = c.get("score", "?")
                home_team_id = c.get("team", {}).get("id")
            else:
                away_score   = c.get("score", "?")
                away_team_id = c.get("team", {}).get("id")

        home_wp = away_wp = None
        wp_series = data.get("winprobability", [])
        if wp_series:
            last    = wp_series[-1]
            home_wp = round(last["homeWinPercentage"] * 100)
            away_wp = 100 - home_wp

        seconds_remaining = None
        try:
            if ":" in clock:
                parts = clock.split(":")
                seconds_remaining = int(parts[0]) * 60 + int(float(parts[1]))
            else:
                seconds_remaining = int(float(clock))
            quarters_left     = max(0, 4 - period)
            seconds_remaining += quarters_left * 12 * 60
        except (ValueError, IndexError):
            pass

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
            "seconds_remaining": seconds_remaining,
            "possession":        possession,
            "detail":            detail,
        }

    except Exception as e:
        return {"game_id": game_id, "game_state": "error", "error": str(e)}


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_kelly(k: dict) -> str:
    if not k["valid"]:
        return f"— ({k['reason']})"
    return (f"f*={k['f_star']:.1%}  "
            f"${k['dollars']:.0f}  "
            f"{k['contracts']} contracts  "
            f"EV ${k['ev']:.2f}")


def fmt_entry(eq: dict) -> str:
    sizing = (
        f"  f_max={eq['f_max']:.1%} ({eq['kelly_multiplier']:.2f}x Kelly)  "
        f"${eq['dollars']:.0f}  {eq['contracts']} contracts  EV ${eq['ev']:.2f}"
        if eq["f_max"] > 0 else "  no sizing"
    )
    return (
        f"{eq['recommendation']}  "
        f"score={eq['score']}  "
        f"survival={eq['survival']:.0%}  "
        f"vol={eq['vol_remaining']:.3f}  "
        f"edge={eq['raw_edge']:+.1%}"
        f"{sizing}"
    )


# ── Print + trade ─────────────────────────────────────────────────────────────

def print_and_trade(row, espn: dict, prices: dict, client, dry_run: bool = False):
    game_id     = row["game_id"]
    ticker      = row["ticker"]
    home_code   = get_team_code(row["home_team"])
    away_code   = get_team_code(row["away_team"])
    yes_team    = get_yes_team_from_ticker(ticker)
    yes_is_home = yes_team == home_code

    if espn.get("game_state") == "final":
        print(f"Game {game_id}: FINAL")
        return
    if espn.get("game_state") == "error":
        print(f"Game {game_id}: ERROR — {espn.get('error')}")
        return

    print(f"  [DEBUG] raw prices: yes_bid={prices.get('yes_bid')}  "
          f"yes_ask={prices.get('yes_ask')}  "
          f"no_bid={prices.get('no_bid')}  "
          f"no_ask={prices.get('no_ask')}  "
          f"yes_team={yes_team}  yes_is_home={yes_is_home}")

    if yes_is_home:
        home_yes_bid, home_yes_ask = prices.get("yes_bid", "?"), prices.get("yes_ask", "?")
        away_yes_bid, away_yes_ask = prices.get("no_bid",  "?"), prices.get("no_ask",  "?")
        home_side, away_side       = "yes", "no"
    else:
        home_yes_bid, home_yes_ask = prices.get("no_bid",  "?"), prices.get("no_ask",  "?")
        away_yes_bid, away_yes_ask = prices.get("yes_bid", "?"), prices.get("yes_ask", "?")
        home_side, away_side       = "no", "yes"

    home_espn_wp = espn.get("home_wp")
    away_espn_wp = espn.get("away_wp")
    secs         = espn.get("seconds_remaining")
    period       = espn.get("period", 0)

    def calc_edge(espn_wp, yes_ask):
        try:
            return round((float(espn_wp) / 100) - (float(yes_ask) / 100), 4)
        except (TypeError, ValueError):
            return None

    def fmt_edge(e):
        return f"{e:+.2%}" if e is not None else "?"

    home_edge = calc_edge(home_espn_wp, home_yes_ask)
    away_edge = calc_edge(away_espn_wp, away_yes_ask)

    home_kelly = full_kelly(
        true_probability = home_espn_wp / 100 if home_espn_wp is not None else None,
        kalshi_ask       = home_yes_ask,
    )
    away_kelly = full_kelly(
        true_probability = away_espn_wp / 100 if away_espn_wp is not None else None,
        kalshi_ask       = away_yes_ask,
    )

    if espn["game_state"] == "pre":
        print(f"Game {game_id}:")
        print(f"  {home_code} vs {away_code}  —  {espn.get('detail', 'Scheduled')}")
        print(f"  {home_code}  ESPN: {home_espn_wp}%  Bid: {home_yes_bid}  Ask: {home_yes_ask}  "
              f"Edge: {fmt_edge(home_edge)}  Kelly: {fmt_kelly(home_kelly)}")
        print(f"  {away_code}  ESPN: {away_espn_wp}%  Bid: {away_yes_bid}  Ask: {away_yes_ask}  "
              f"Edge: {fmt_edge(away_edge)}  Kelly: {fmt_kelly(away_kelly)}")
        print("-" * 60)
        print()
        return

    home_score = espn.get("home_score", "?")
    away_score = espn.get("away_score", "?")
    clock      = f"{espn['period_str']} {espn['clock']}"
    poss       = espn.get("possession") or "—"

    try:
        home_score_diff = int(home_score) - int(away_score)
        away_score_diff = -home_score_diff
    except (TypeError, ValueError):
        home_score_diff = away_score_diff = 0

    no_data = {
        "valid": True, "score": 0, "recommendation": "— no data",
        "raw_edge": 0, "survival": 0, "vol_remaining": 0,
        "velocity": 0, "f_max": 0, "f_star": 0,
        "kelly_multiplier": 0, "dollars": 0, "contracts": 0, "ev": 0,
    }

    def can_compute(wp, ask):
        return wp is not None and secs is not None and isinstance(ask, (int, float))

    home_entry = entry_quality(
        p_current         = home_espn_wp / 100,
        kalshi_ask        = home_yes_ask,
        seconds_remaining = secs or 0,
        score_diff        = home_score_diff,
        period            = period,
    ) if can_compute(home_espn_wp, home_yes_ask) else no_data

    away_entry = entry_quality(
        p_current         = away_espn_wp / 100,
        kalshi_ask        = away_yes_ask,
        seconds_remaining = secs or 0,
        score_diff        = away_score_diff,
        period            = period,
    ) if can_compute(away_espn_wp, away_yes_ask) else no_data

    print(f"Game {game_id}:")
    print(f"  {home_code}: {home_score} pts  ESPN: {home_espn_wp}%  "
          f"Bid: {home_yes_bid}  Ask: {home_yes_ask}  "
          f"Edge: {fmt_edge(home_edge)}  Kelly: {fmt_kelly(home_kelly)}")
    print(f"    Entry: {fmt_entry(home_entry)}")
    print(f"  {away_code}: {away_score} pts  ESPN: {away_espn_wp}%  "
          f"Bid: {away_yes_bid}  Ask: {away_yes_ask}  "
          f"Edge: {fmt_edge(away_edge)}  Kelly: {fmt_kelly(away_kelly)}")
    print(f"    Entry: {fmt_entry(away_entry)}")
    print(f"  Clock: {clock}   Possession: {poss}")

    # ── Live trading ──────────────────────────────────────────────────
    for team_code, entry, side, ask in [
        (home_code, home_entry, home_side, home_yes_ask),
        (away_code, away_entry, away_side, away_yes_ask),
    ]:
        result = maybe_trade(
            client    = client,
            ticker    = ticker,
            side      = side,
            entry     = entry,
            ask_price = int(ask) if isinstance(ask, (int, float)) else 0,
            dry_run   = dry_run,
        )
        if result and result["status"] in ("placed", "dry_run"):
            cost = result["contracts"] * (int(ask) / 100)
            print(f"  {'[DRY RUN] ' if dry_run else ''}⚡ TRADE: {team_code}  "
                  f"{side.upper()}  {result['contracts']} contracts @ {ask}¢  "
                  f"cost ~${cost:.2f}  survival={entry['survival']:.0%}  "
                  f"score={entry['score']}")

    print("-" * 60)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Set dry_run=True to see all signals without placing real orders.
    # Set dry_run=False to trade live.
    DRY_RUN = False

    eastern = pytz.timezone("US/Eastern")
    now_est = datetime.datetime.now(eastern)
    c_client = get_kalshi_client()

    for league in ["nba", "ncaabbm", "ncaabbw"]:
        espn_games   = pandas.read_json(f"espn_games_{league}.json")
        kalshi_games = pandas.read_json(f"kalshi_games_{league}.json")
        print(f"Loaded {len(espn_games)} ESPN games and "
              f"{len(kalshi_games)} Kalshi games for {league}")

        espn_games["home_team"]   = espn_games["home_team"].apply(
            lambda x: get_team_code(x, league))
        espn_games["away_team"]   = espn_games["away_team"].apply(
            lambda x: get_team_code(x, league))
        kalshi_games["home_team"] = kalshi_games["home_team"].apply(
            lambda x: normalize_team_code(x, league))
        kalshi_games["away_team"] = kalshi_games["away_team"].apply(
            lambda x: normalize_team_code(x, league))

        kalshi_lookup = {}
        for _, row in kalshi_games.iterrows():
            key = (row["date"], frozenset([row["home_team"], row["away_team"]]))
            kalshi_lookup[key] = row

        merged_rows = []
        for _, espn_row in espn_games.iterrows():
            key        = (espn_row["date"],
                          frozenset([espn_row["home_team"], espn_row["away_team"]]))
            kalshi_row = kalshi_lookup.get(key)
            if kalshi_row is not None:
                if (espn_row["home_team"] == kalshi_row["home_team"] and
                        espn_row["away_team"] == kalshi_row["away_team"]):
                    merged = {**espn_row, **kalshi_row}
                else:
                    swapped = kalshi_row.copy()
                    swapped["home_team"], swapped["away_team"] = (
                        swapped["away_team"], swapped["home_team"])
                    merged = {**espn_row, **swapped}
                merged_rows.append(merged)
            else:
                print(f"  [NO MATCH] {espn_row['home_team']} vs "
                      f"{espn_row['away_team']} on {espn_row['date']}")

        if not merged_rows:
            print(f"  No matched games for {league}")
            continue

        merged = pandas.DataFrame(merged_rows)

        def get_game_time(row):
            time_str = row.get("time")
            if not time_str:
                return datetime.datetime.max.replace(tzinfo=eastern)
            try:
                return parser.parse(time_str).astimezone(eastern)
            except Exception:
                return datetime.datetime.max.replace(tzinfo=eastern)

        merged["_game_time"] = merged.apply(get_game_time, axis=1)
        merged = merged.sort_values("_game_time")

        for _, row in merged.iterrows():
            game_time = row.get("_game_time")
            if game_time and now_est < game_time:
                print(f"Game {row['game_id']}: {row['home_team']} vs "
                      f"{row['away_team']}  —  "
                      f"{game_time.strftime('%m/%d - %I:%M %p EST')} (Not started)")
                print("-" * 60)
                print()
                continue

            prices = get_kalshi_prices(row["ticker"], c_client)
            espn   = get_live_state(row["game_id"], league)
            print_and_trade(row, espn, prices, c_client, dry_run=DRY_RUN)