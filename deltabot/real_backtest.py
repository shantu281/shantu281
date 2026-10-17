"""Backtest on real Delta option prices (downloaded chains, see option_data.py).

Each leg is valued from its own 5-minute candles (mark or traded price). Strike
selection reuses the strategies: the at-the-money implied vol is backed out of
the real prices, the strategy picks strikes by delta, and each strike is snapped
to the nearest listed strike that has data. Stops are checked against the worst
combination of leg highs/lows in each bar, so they are conservative. Expiry
settles on the average of the index over the last 30 minutes, like Delta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import BacktestConfig, Trade, _leg_cost
from .option_data import load_chain
from .pricing import SECONDS_PER_YEAR, implied_vol, intrinsic
from .strategies import EntryContext, Leg, Strategy


@dataclass
class RealConfig(BacktestConfig):
    hours_before: float = 24.0       # enter this long before the 12:00 UTC expiry
    settle_minutes: int = 30         # settlement = average index over the last N minutes
    min_price: float = 1.0           # skip legs priced below this (USD per BTC): no real market


def _align(df: pd.DataFrame, times: pd.DatetimeIndex) -> pd.DataFrame:
    """Leg candles on the bar grid; a bar with no print carries the last close flat."""
    a = df.reindex(times)
    a["close"] = a["close"].ffill()
    for col in ("open", "high", "low"):
        a[col] = a[col].fillna(a["close"])
    return a


def _snap(chain, kind: str, strike: float, entry: pd.Timestamp) -> float | None:
    strikes = [k for (kd, k), df in chain.items() if kd == kind and entry in df.index]
    return min(strikes, key=lambda k: abs(k - strike)) if strikes else None


def run_real_backtest(index: pd.DataFrame, chains_dir: str | Path, strategy: Strategy,
                      cfg: RealConfig, start: str | None = None, end: str | None = None) -> list[Trade]:
    """`index`: BTC index candles (5m) indexed by bar open time; `chains_dir`: per-expiry chain files."""
    files = sorted(Path(chains_dir).glob("*.csv.gz"))
    bar = index.index.to_series().diff().mode().iloc[0]
    hourly = index["close"].resample("1h").last().dropna()
    trades: list[Trade] = []

    for f in files:
        expiry = pd.Timestamp(f.name[:10] + " 12:00", tz="UTC")
        if (start and expiry < pd.Timestamp(start, tz="UTC")) or (end and expiry > pd.Timestamp(end, tz="UTC")):
            continue
        entry = expiry - pd.Timedelta(hours=cfg.hours_before)
        if entry not in index.index:
            continue
        chain = load_chain(f)
        spot0 = float(index.loc[entry, "open"])
        t0 = (expiry - entry).total_seconds() / SECONDS_PER_YEAR

        # implied vol from the at-the-money call and put
        atm = _snap(chain, "call", spot0, entry)
        if atm is None or ("put", atm) not in chain or entry not in chain[("put", atm)].index:
            continue
        ivs = [implied_vol(kd, chain[(kd, atm)].loc[entry, "open"], spot0, atm, t0) for kd in ("call", "put")]
        ivs = [v for v in ivs if v]
        if not ivs:
            continue
        iv = sum(ivs) / len(ivs)
        strikes = sorted({k for (_, k) in chain})
        step = float(pd.Series(strikes).diff().median()) if len(strikes) > 1 else cfg.strike_step

        ctx = EntryContext(entry, spot0, t0, iv, hourly.loc[:entry - bar].to_frame("close"), step)
        wanted = strategy.legs(ctx)
        if not wanted:
            continue
        legs = []
        for l in wanted:
            k = _snap(chain, l.kind, l.strike, entry)
            if k is None:
                break
            legs.append(Leg(l.kind, k, l.side))
        # a leg that snapped onto another leg's strike would change the structure: skip the day
        if len(legs) != len(wanted) or len({(l.kind, l.strike) for l in legs}) != len(legs):
            continue
        data = [chain[(l.kind, l.strike)] for l in legs]
        p0 = [float(d.loc[entry, "open"]) for d in data]
        if min(p0) < cfg.min_price:
            continue

        v0 = sum(l.side * p for l, p in zip(legs, p0))
        basis = abs(v0)
        costs = sum(_leg_cost(cfg, spot0, p) for p in p0)
        stop = -strategy.stop_mult * basis if strategy.stop_mult is not None else None
        target = strategy.take_profit * basis if strategy.take_profit is not None else None

        times = pd.date_range(entry, expiry - bar, freq=bar)
        aligned = [_align(d, times) for d in data]
        sides = np.array([l.side for l in legs], dtype=float)

        def value(long_field: str, short_field: str):
            cols = [a[long_field if l.side > 0 else short_field].to_numpy() for l, a in zip(legs, aligned)]
            return (sides[:, None] * np.vstack(cols)).sum(axis=0) - v0

        pnl_open, worst, best = value("open", "open"), value("low", "high"), value("high", "low")
        exit_reason, exit_time, exit_pnl, exit_prices = "expiry", expiry, None, None
        for i, ts in enumerate(times):
            if stop is not None and (pnl_open[i] <= stop or worst[i] <= stop):
                exit_reason, exit_pnl = "stop", min(pnl_open[i], stop)
            elif target is not None and (pnl_open[i] >= target or best[i] >= target):
                exit_reason, exit_pnl = "target", max(pnl_open[i], target)
            else:
                continue
            exit_time = ts + bar
            exit_prices = [float(a["close"].iloc[i]) for a in aligned]
            break

        spot_exit = float(index.loc[:exit_time - bar, "close"].iloc[-1])
        if exit_reason == "expiry":
            window = index.loc[expiry - pd.Timedelta(minutes=cfg.settle_minutes): expiry - bar, "close"]
            if window.empty:
                continue
            spot_exit = float(window.mean())
            settle = [intrinsic(l.kind, spot_exit, l.strike) for l in legs]
            exit_pnl = sum(l.side * s for l, s in zip(legs, settle)) - v0
            if cfg.settlement_fee:
                costs += sum(_leg_cost(cfg, spot_exit, s, settle=True) for s in settle if s > 0)
        else:
            costs += sum(_leg_cost(cfg, spot_exit, p) for p in exit_prices)

        trades.append(Trade(strategy.name, entry, exit_time, expiry, spot0, spot_exit, iv, legs, v0,
                            exit_reason, exit_pnl * cfg.qty_btc, costs * cfg.qty_btc))
    return trades
