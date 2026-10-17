# Handoff: Delta Exchange India BTC options bot

You are continuing a project started in a cloud session that could not reach Delta Exchange. **You run on the user's Windows PC, which can.** Do every step below yourself, in order, and report the results in plain, simple language. The user is a trader, not a programmer, so keep explanations short and avoid jargon.

## Goal
Build a bot that trades **BTC options on Delta Exchange India**. Backtest first and pick the strategy that holds up, then paper trade, then go live. Right now we are at the **backtest** stage.

## What has been established (checked by the user on 17 Oct 2026)
- Delta keeps **expired option contracts**, with candles per symbol, e.g. `C-BTC-57000-270924` (traded price) and `MARK:C-BTC-57000-270924` (mark price).
- There are 94,564 expired BTC options. The oldest is Dec 2023 (0 candles). **From Sep 2024 onward, data is full**: 577 of 577 five-minute mark candles over 48 hours, and 541–572 traded candles.
- So we backtest on **real Delta option prices at 5-minute resolution, from Sep 2024 to now**.
- No API key is needed for data. **Never ask the user to paste an API secret into chat.**

## Code (already written and tested on synthetic data)
- GitHub repo `shantu281/shantu281`, branch **`claude/code-session-jlw1o5`**. Read `README.md` first.
- `deltabot/client.py`: Delta India REST client.
- `deltabot/option_data.py`: downloads expired option chains (one gzipped CSV per daily expiry).
- `deltabot/real_backtest.py`: backtest on real option prices.
- `deltabot/backtest.py`: model-priced fallback.
- `deltabot/strategies.py`: 7 candidates (short straddle, with and without exits; short strangle at 20 and 10 delta; iron condor; long straddle; trend-following option buying).
- `scripts/download_options.py`, `scripts/run_real_backtest.py`
- Tests: `python -m pytest -q` (16 pass). The code has **never run against the real API**, so expect to fix small things such as field names, the index symbol, or rate limits.

## Steps to do now
1. **Get the code.** If this folder isn't already the repo:
   `git clone https://github.com/shantu281/shantu281.git delta-bot`, then `cd delta-bot`, then `git checkout claude/code-session-jlw1o5`.
   If git is missing, install it with `winget install --id Git.Git -e`.
2. Run `pip install -r requirements.txt`, then `python -m pytest -q`.
3. **Test one month:** `python scripts/download_options.py --start 2026-09-01 --end 2026-09-30`
   - If the `.DEXBTUSD` index fails, the script falls back to `BTCUSD`. Check which one was used.
   - Check that the files in `data/options/` contain sensible strikes and prices. Open one and look at it.
   - Fix any API or format errors in the code. Commit each fix with a clear message.
4. Run `python scripts/run_real_backtest.py` and show the user the strategy table, in simple words.
5. **Sanity checks before trusting any result:**
   - Is the at-the-money implied vol plausible (usually 30–80% for BTC)?
   - Do entry premiums look like real Delta prices?
   - Are trades skipped on many days? Explain why.
6. If the month looks right, start the **full download**: `python scripts/download_options.py --start 2024-09-01`. It takes a few hours and can be resumed. Run it in the background, then rerun the backtest on the full history and give a month-by-month table.
7. Commit and push code changes to `claude/code-session-jlw1o5`. Don't commit `data/` or `results/`; they're gitignored.

## Open items to raise with the user
- **Fees are assumed, not checked:** 0.03% of notional per leg, capped at 3.5% of the premium, plus 18% GST, and slippage of 2% of the premium (minimum $5 per BTC). Ask the user to confirm them from their Delta fee page, or look them up, and update `BacktestConfig` in `deltabot/backtest.py`.
- **Mark price is not a fill price.** Later, compare mark prices with traded prices (`--price trade`) to estimate the real spread.
- The user also uses AlgoTest (algotest.in), which backtests Delta BTC options. Its results can be used as a cross-check.

## Working rules the user asked for
- **Say clearly what is checked and what is a guess.** An earlier unchecked "no real data exists" claim sent the project the wrong way.
- Keep answers short and simple. Ask before big direction changes.
- Don't edit trading files or settings the user didn't ask about.
