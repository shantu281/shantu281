"""Engine mechanics on synthetic candles (not market results)."""

import numpy as np
import pandas as pd

from deltabot.backtest import BacktestConfig, run_backtest, summarise, trades_frame
from deltabot.strategies import LongStraddle, ShortStraddle


def make_candles(days, drift_per_bar=0.0, noise=0.002, seed=0):
    idx = pd.date_range("2024-01-01", periods=24 * days, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 60_000 * np.exp(np.cumsum(drift_per_bar + noise * rng.standard_normal(len(idx))))
    open_ = np.r_[60_000, close[:-1]]
    return pd.DataFrame({"open": open_, "close": close,
                         "high": np.maximum(open_, close) * 1.0005,
                         "low": np.minimum(open_, close) * 0.9995}, index=idx)


def zero_cost():
    return BacktestConfig(fee_rate=0, slippage_pct=0, min_slippage=0, settlement_fee=False)


def test_one_trade_per_day_and_settles_at_expiry():
    trades = run_backtest(make_candles(20), ShortStraddle("ss"), zero_cost())
    assert len(trades) == 12  # 7-day vol lookback, last day has no full expiry window
    for t in trades:
        assert t.exit_reason == "expiry"
        assert (t.expiry - t.entry_time) == pd.Timedelta(hours=24)


def test_short_straddle_loses_on_a_strong_trend_and_stop_caps_it():
    candles = make_candles(30, drift_per_bar=0.004, noise=0.0005)
    no_stop = trades_frame(run_backtest(candles, ShortStraddle("a"), zero_cost()))
    with_stop = trades_frame(run_backtest(candles, ShortStraddle("b", stop_mult=1.0), zero_cost()))
    assert no_stop["pnl"].sum() < 0
    assert (with_stop["exit_reason"] == "stop").any()
    assert with_stop["pnl"].min() >= no_stop["pnl"].min()
    # long straddle is the mirror image when costs are zero
    long_ = trades_frame(run_backtest(candles, LongStraddle("c"), zero_cost()))
    assert long_["pnl"].sum() == -no_stop["pnl"].sum()


def test_costs_reduce_pnl():
    candles = make_candles(20)
    gross = summarise(trades_frame(run_backtest(candles, ShortStraddle("x"), zero_cost())))
    net = summarise(trades_frame(run_backtest(candles, ShortStraddle("x"), BacktestConfig())))
    assert net["net_pnl"] < gross["net_pnl"]
    assert net["costs"] > 0


def test_market_structure_reads_swings():
    from deltabot.strategies import market_structure
    zigzag = np.tile(np.r_[np.linspace(0, 10, 6), np.linspace(10, 0, 6)[1:-1]], 8)
    drift = np.arange(len(zigzag)) * 0.3
    assert market_structure(pd.Series(100 + zigzag + drift)) == "up"
    assert market_structure(pd.Series(100 + zigzag - drift)) == "down"
    assert market_structure(pd.Series(100 + zigzag)) == "range"


def test_move_adaptive_seller_widens_with_movement():
    from deltabot.strategies import EntryContext, MoveAdaptiveSeller
    times = pd.date_range("2026-01-01", periods=200, freq="1h", tz="UTC")
    quiet = pd.DataFrame({"close": 80_000 + 50 * np.sin(np.arange(200))}, index=times)
    wild = pd.DataFrame({"close": 80_000 + 800 * np.sin(np.arange(200))}, index=times)
    strat = MoveAdaptiveSeller("m", params={"width": 1.0})

    def gap(hist):
        legs = strat.legs(EntryContext(times[-1], 80_000, 2 / (365 * 24), 0.3, hist, 100))
        call, put = (l.strike for l in legs)
        return call - put

    assert gap(wild) > gap(quiet) >= 0


def test_gmma_state_and_option_side():
    from deltabot.strategies import EntryContext, GmmaOptionSeller, gmma_state
    rising = pd.Series(np.linspace(60_000, 80_000, 300))
    assert gmma_state(rising) == "up"
    assert gmma_state(rising[::-1].reset_index(drop=True)) == "down"
    times = pd.date_range("2026-01-01", periods=300 * 4, freq="1h", tz="UTC")
    hist = pd.DataFrame({"close": np.linspace(60_000, 80_000, len(times))}, index=times)
    ctx = EntryContext(times[-1] + pd.Timedelta(hours=1), 80_000, 2 / (365 * 24), 0.3, hist, 100)
    (leg,) = GmmaOptionSeller("g").legs(ctx)
    assert (leg.kind, leg.side) == ("put", -1)
