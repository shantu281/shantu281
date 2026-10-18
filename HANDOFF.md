# Handoff: Delta Exchange India BTC options bot (status 18 Oct 2026)

Paste or upload this file at the start of a new session. The user is a trader, not a
programmer: short plain answers, month-wise tables, say clearly what is checked and what
is a guess, ask before big direction changes, don't start new research unprompted.

## Where things are
- Repo `shantu281/shantu281`, branch `claude/hopeful-goodall-9poj0b`. Tests: `python -m pytest -q` (21 pass).
- Data is not in git. Rebuild: `python scripts/download_options.py --start 2024-09-01` (~1 hour; needs network access to `api.india.delta.exchange`), then prepend BTC index 5m candles from 2024-05-01 (the GMMA EMAs need warm-up; see `research/README.md`).
- Backtest: `python scripts/run_real_backtest.py --hours-before 8 --strategies gmma_sell_otm --lots 100`.
- Research scripts: `research/`.

## What was established (real Delta mark prices, 5-min, Sep 2024 to Oct 2026)
- Checked: 1 BTC option lot = 0.001 BTC. Fees 0.010% of notional capped at 3.5% of premium, +18% GST, no fee on OTM expiry (user, from Delta's fee page).
- Guess: spread/slippage max(2% of premium, $5 per BTC) per leg trade. A live order-book snapshot (Sat 02:10 IST, many crossed quotes) showed $2-3 spreads on cheap OTM options.
- Selling the day before expiry loses in every version. Selling on expiry day, 2-8 h before 17:30 IST, can work.
- Bugs fixed: profit targets used mixed intrabar extremes (now bar close); newly listed options' first candle opens at a placeholder ($0.10) and is dropped.

## Best 3 (100 lots per leg, real fees, $5 spread, 2 years)
| # | Strategy | Net | Worst drop | Notes |
|---|---|---|---|---|
| 1 | GMMA H4 seller, 09:30 IST, strike 0.5x recent move OTM, hold to expiry (`gmma_sell_otm`, 8 h) | +$2,038 | -$473 | Works 2-8 h before expiry, both years positive, beat 98% of random-side controls |
| 2 | Leaning strangle, 15:30 IST, 1x stop (`research/gfilter.py` mode "skew") | +$1,912 | -$316 | Only works within ~4 h of expiry |
| 3 | GMMA H4 seller, 15:30 IST, 1x stop | +$874 | -$124 | Safest; worst day -$27 |
GMMA: EMAs 3,5,8,10,12,15 vs 30,35,40,45,50,60 on completed H4 closes (UTC-aligned bars). Ribbon up = sell put, down = sell call, tangled = no trade.

All three together: +$4,597, PF 1.41, win 69.8%, max drawdown -$602, 5 of 25 losing months.

## $1,000 account
- Isolated/cross margin for a naked short option is 10-15% of BTC value per lot (user's source cites a video; check on Delta's order screen). Fully used: $1,000 -> $2,366-$3,600 over 2 years, max drawdown 13-20%.
- Portfolio margin is only ~1% per lot (computed from Delta's guide); fully used it wiped the account out on 5 Mar 2025. Use isolated mode, or cap size in the bot.

## Greeks research
- Filters (14 Greek/vol measures): none helped out of sample.
- Strike by delta: no better than the move-based strike. Delta-based exits: hurt.
- Lead: size lots by implied vol (lots x IV / median IV of last 60 trades, clipped 0.5-2x). Better in both years for every strategy; drawdowns usually 15-30% bigger, except #3 where everything improved.

## Option buying (parked by the user, 18 Oct 2026: "buying is out for now")
- Hero-zero at fixed times (ATM to 1.5% OTM, 1-3 h before expiry): loses in every version, even before costs (`research/hero.py`).
- Triggered buying (`research/hero_signal.py`, `research/hero_combo.py`): only a 5-30 min momentum burst in the GMMA H4 trend direction works; against the trend it always loses. Best: 0.5% OTM, take profit 5x: +$1,076 over 2 years at 100 lots, but year 2 was +$3; 3x targets and premium caps made it worse.
- Combined with the 3 sellers it adds ~$1,000 (all year 1), slightly bigger drawdown, and no protection on the sellers' worst days. Not used.

## Insurance for the GMMA seller (tested 18 Oct 2026, dropped by the user)
- P&L stops 1-5x premium and bought wings further OTM (1-3x size) all cost more than they save (`research/insurance.py`). The 3x stop was the least bad (+$1,449 vs +$2,038, smaller bad months); the user judged it not useful. Run the seller uninsured at small size.

## Iron butterfly (user likes it; added 18 Oct 2026)
- `IronButterfly("iron_fly_2pct_iv32")`: at 15:30 IST (2 h before expiry) sell the ATM call+put, buy a call and a put 2% away, hold to expiry, only when ATM implied vol >= 32%. Run: `python scripts/run_real_backtest.py --hours-before 2 --min-price 0.1 --strategies iron_fly_2pct_iv32` -> +$1,270 at 100 lots, PF 1.66, max drawdown -$324.
- Risk rules (`deltabot/risk.py`): size lots by margin (user: ~5% per sold leg) and stop trading for the rest of the month once the month is down 10% (`MonthlyStop`). With $500 fresh each month: +$787 over 26 months, worst month -$75.
- Variations that did not help: cheap wings every day, move-based wings, GMMA-shifted centre, other entry times, IV-based lot sizing (`research/ifly_boost.py`).

## Next steps (ask the user first)
1. Paper-trading bot for #1 and #3 (optionally #2, and IV sizing), live Delta prices, no orders.
2. Confirm margin per lot on Delta's order screen.
3. Compare paper fills with mark prices to measure the real spread.
4. Only then go live small (10-20 lots), isolated margin.

## Related
- The user's "bot 2" sessions (on their PC, MT5) hold a gold strategy (GMMA + Inside-day + Turtle soup) and a Bitcoin GMMA H4 futures lead on Vantage; those MT5 tests can't run from a cloud session.
