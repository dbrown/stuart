# Kalshi NBA Live Trader

Exploits longshot bias in Kalshi prediction markets by buying high-probability contracts (≥75¢) when ESPN's live win-probability model shows ≥6% edge over Kalshi's market price.

## Module structure

```
nba/
├── config.py           # All constants, credentials, endpoints, mappings
├── fees.py             # Kalshi fee formula (pure, testable)
├── kelly.py            # Kelly criterion + drawdown-constrained sizing
├── entry.py            # Entry quality scoring, survival probability, period gate
├── teams.py            # Kalshi ↔ ESPN team code normalization
├── espn.py             # ESPN API: scoreboard + live game state
├── kalshi_client.py    # Kalshi API: client, prices, orders, maybe_trade()
├── merge.py            # Join ESPN + Kalshi game lists by (date, teams)
├── display.py          # Terminal output + per-game trade orchestration
├── get_espn_games.py   # Script: fetch today's ESPN games → JSON
├── get_kalshi_games.py # Script: fetch today's Kalshi markets → JSON
├── main.py             # Entry point: load JSON, merge, run trading loop
└── tests/
    └── test_all.py     # Unit tests (no network, no credentials)
```

## Workflow

```bash
# 1. Populate today's game data (run once, or re-run to refresh)
python get_espn_games.py
python get_kalshi_games.py

# 2. Run trading loop (dry run by default)
python main.py

# 3. Go live
python main.py --live
```

## Testing

```bash
pip install pytest scipy
python -m pytest tests/ -v
```

## Configuration

All tunable parameters live in `config.py`:

| Constant      | Default | Meaning                                  |
|---------------|---------|------------------------------------------|
| `BANKROLL`    | 288.0   | Total capital in dollars                 |
| `MAX_TRADE`   | 20.0    | Hard cap per trade in dollars            |
| `MIN_PRICE`   | 75      | Minimum Kalshi ask in cents              |
| `MIN_EDGE`    | 0.06    | Minimum ESPN vs Kalshi edge (decimal)    |
| `MIN_SURVIVAL`| 0.70    | Minimum WP survival probability          |
| `USE_MAKER`   | True    | Post-only orders (lower fees)            |
| `DRY_RUN`     | True    | Set False to place real orders           |
