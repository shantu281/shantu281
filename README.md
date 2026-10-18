# Delta Exchange India: BTC options bot

The plan is to backtest several BTC option strategies, pick the one that holds up, then run it on paper and finally live.

## Status

| Part | State |
|---|---|
| REST client (`deltabot/client.py`) | Public data and signed orders written, not yet run against the live API |
| Pricing (`deltabot/pricing.py`) | Black-Scholes price, delta and strike-by-delta; tested |
| Real-price backtest (`deltabot/real_backtest.py`, `deltabot/option_data.py`) | Uses Delta's own 5-minute option candles; tested on synthetic chains, not yet run on real data |
| Model-priced backtest (`deltabot/backtest.py`) | Black-Scholes fallback; tested on synthetic data |
| Candidate strategies (`deltabot/strategies.py`) | Short straddle, short strangle (20Δ / 10Δ), iron condor, long straddle, trend-following option buying, market-structure seller (put in uptrend, call in downtrend, straddle in range), movement-spaced strangle (strikes set by recent BTC moves), GMMA H4 seller (put when the ribbon points up, call when down), iron butterfly (2% wings) |
| Paper and live runner | Not started; it comes after a strategy is chosen |

## Setup

```bash
pip install -r requirements.txt
python -m pytest -q
```

## Real-price backtest (main path)

Delta keeps every expired BTC option with its 5-minute candles (checked on 17 Oct 2026: 94,564 expired BTC options; full mark-price and traded candles from Sep 2024 on, none for the oldest Dec 2023 contract).

```bash
python scripts/download_options.py --start 2026-09-01 --end 2026-09-30   # one month first
python scripts/download_options.py --start 2024-09-01                    # full history, a few hours, resumable
python scripts/run_real_backtest.py                                      # compare all strategies
```

- The download saves the BTC index, the list of options, and one file per daily expiry, holding every strike within ±5% of spot (`data/options/YYYY-MM-DD.csv.gz`). It uses mark prices by default; pass `--price trade` for traded prices.
- The backtest reads the at-the-money implied vol from the real prices and picks strikes by delta. It values each leg from its own candles, checks stops against the worst high/low combination in each bar, checks profit targets only on the bar close, and settles on the 30-minute average of the index.
- Mark price is not a fill price, so the spread cost (`slippage_pct`, `min_slippage`) still matters.

## Model-priced backtest (fallback)

### 1. Download BTC candles

```bash
python scripts/download_data.py --symbol BTCUSD --resolution 1h --start 2023-01-01
```

This saves `data/BTCUSD_1h.csv`. It needs network access to `api.india.delta.exchange`.

### 2. Compare strategies

```bash
python scripts/run_backtest.py --data data/BTCUSD_1h.csv --iv-mult 0.9 1.0 1.2
```

For each implied-vol assumption, the script prints a summary per strategy: net P&L, win rate, profit factor, max drawdown, worst trade and losing months. It also writes the trade lists and month-wise tables to `results/`.

## How the backtest works, and its limits

- **Daily options:** Delta India's daily BTC options expire at 17:30 IST (12:00 UTC). By default the bot enters at 12:00 UTC into the next day's expiry, a 24-hour option. Use `--entry-hour` to change the entry time; an entry before 12:00 UTC trades the same day's expiry.
- **Prices are modelled, not historical.** Each leg is priced with Black-Scholes from the BTC candles, using an implied vol equal to the trailing 7-day realised vol × `iv_mult`.
  - Real BTC implied vol is usually *above* realised vol, which is the edge premium sellers earn. So `iv_mult` largely decides whether selling looks good.
  - Always compare strategies across several `iv_mult` values.
  - Next step: check `iv_mult` against real Delta option prices.
- **Stops and targets:** the engine checks them on every bar using the bar's high and low. If both hit in the same bar, it assumes the stop came first. A gap through the stop fills at the bar's open.
- **Costs:** 0.010% of notional per leg, capped at 3.5% of the premium, plus 18% GST; out-of-the-money legs settle free (Delta India fee page, checked 18 Oct 2026). Slippage of 2% of the premium, with a minimum of $5 per BTC, is still a guess (`BacktestConfig`).
- **Settlement:** expiry settles on the close of the last candle before expiry. Delta settles on a 30-minute average of the index.

## Layout

```
deltabot/
  client.py      Delta India REST client (public + HMAC-signed private endpoints)
  data.py        candle download / load
  pricing.py     Black-Scholes, delta, strike selection
  strategies.py  candidate strategies and their exit rules
  backtest.py    engine, trade table, summary stats, month-wise table
scripts/
  download_data.py
  run_backtest.py
tests/
```
