"""Real-price engine mechanics on a synthetic chain priced with Black-Scholes (not market results)."""

import numpy as np
import pandas as pd
import pytest

from deltabot.option_data import load_chain, parse_symbol
from deltabot.pricing import SECONDS_PER_YEAR, bs_price, implied_vol
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import IronCondor, ShortStraddle, ShortStrangle

VOL = 0.5


def make_index(days=4, noise=0.0008, seed=1):
    idx = pd.date_range("2025-05-01", periods=288 * days, freq="5min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 95_000 * np.exp(np.cumsum(noise * rng.standard_normal(len(idx))))
    open_ = np.r_[95_000, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
                         "close": close}, index=idx)


def write_chain(index, expiry, path, step=500, band=0.06):
    times = index.loc[expiry - pd.Timedelta(hours=26): expiry - pd.Timedelta(minutes=5)].index
    spot = index.loc[times[0], "open"]
    rows = []
    for k in np.arange(round(spot * (1 - band) / step) * step, spot * (1 + band), step):
        for kind in ("call", "put"):
            sym = f"{kind[0].upper()}-BTC-{int(k)}-{expiry:%d%m%y}"
            for ts in times:
                t = (expiry - ts).total_seconds() / SECONDS_PER_YEAR
                o = bs_price(kind, index.loc[ts, "open"], k, t, VOL)
                c = bs_price(kind, index.loc[ts, "close"], k, t - 300 / SECONDS_PER_YEAR, VOL)
                rows.append({"time": ts, "symbol": sym, "open": o, "high": max(o, c), "low": min(o, c), "close": c})
    pd.DataFrame(rows).to_csv(path, index=False, compression="gzip")


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    d = tmp_path_factory.mktemp("options")
    index = make_index()
    for day in ("2025-05-03", "2025-05-04"):
        expiry = pd.Timestamp(day + " 12:00", tz="UTC")
        write_chain(index, expiry, d / f"{day}.csv.gz")
    return index, d


def zero_cost():
    return RealConfig(fee_rate=0, slippage_pct=0, min_slippage=0, settlement_fee=False)


def test_parse_symbol():
    assert parse_symbol("C-BTC-57000-270924") == ("call", "BTC", 57000.0,
                                                  pd.Timestamp("2024-09-27 12:00", tz="UTC"))


def test_implied_vol_round_trip():
    p = bs_price("put", 95_000, 94_000, 1 / 365, 0.42)
    assert implied_vol("put", p, 95_000, 94_000, 1 / 365) == pytest.approx(0.42, abs=1e-4)


def test_load_chain(setup):
    _, d = setup
    chain = load_chain(d / "2025-05-03.csv.gz")
    assert ("call", 95_000.0) in chain and ("put", 95_000.0) in chain


def test_short_straddle_settles_against_real_prices(setup):
    index, d = setup
    trades = run_real_backtest(index, d, ShortStraddle("ss"), zero_cost())
    assert len(trades) == 2
    for t in trades:
        assert t.exit_reason == "expiry"
        assert t.vol == pytest.approx(VOL, abs=0.01)  # implied vol recovered from the chain
        assert t.entry_premium < 0  # credit
        settle = sum(l.side * max((t.spot_exit - l.strike) if l.kind == "call" else (l.strike - t.spot_exit), 0)
                     for l in t.legs)
        assert t.gross_pnl == pytest.approx((settle - t.entry_premium) * 0.1)


def test_multi_leg_strategies_pick_listed_strikes(setup):
    index, d = setup
    for strat in (ShortStrangle("s", params={"delta": 0.2}), IronCondor("ic", stop_mult=1.5, take_profit=0.6)):
        trades = run_real_backtest(index, d, strat, RealConfig())
        assert trades
        for t in trades:
            assert all(l.strike % 500 == 0 for l in t.legs)
            assert t.costs > 0


def test_target_needs_a_real_close_not_mixed_intrabar_extremes(setup, tmp_path):
    # Each leg's low can come at a different moment in the bar, so the sum of the lows of a short
    # straddle may never have been tradeable. Spiking every low must not change target exits.
    index, d = setup
    for f in d.glob("*.csv.gz"):
        df = pd.read_csv(f, compression="gzip")
        df["low"] = 0.01
        df.to_csv(tmp_path / f.name, index=False, compression="gzip")
    strat = ShortStraddle("ss", take_profit=0.3)
    base = run_real_backtest(index, d, strat, zero_cost())
    spiked = run_real_backtest(index, tmp_path, strat, zero_cost())
    assert [(t.exit_reason, t.exit_time, t.gross_pnl) for t in base] == \
           [(t.exit_reason, t.exit_time, t.gross_pnl) for t in spiked]
