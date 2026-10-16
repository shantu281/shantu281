"""Model-priced backtest for daily-expiry BTC options on Delta Exchange India.

Option prices are not taken from history: each leg is priced with Black-Scholes
using the BTC candles and an implied-vol assumption (trailing realised vol x
`iv_mult`). The implied-vol assumption drives the result, especially for
premium-selling strategies, so compare strategies across several `iv_mult`
values rather than trusting one run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .pricing import SECONDS_PER_YEAR, bs_price, intrinsic
from .strategies import EntryContext, Leg, Strategy


@dataclass
class BacktestConfig:
    qty_btc: float = 0.1             # underlying per leg (Delta India BTC option lot = 0.001 BTC)
    entry_hour_utc: int = 12         # 12:00 UTC = 17:30 IST, right after the daily expiry
    expiry_hour_utc: int = 12        # Delta India daily options expire 17:30 IST
    strike_step: float = 200.0       # strike spacing used for strike selection
    vol_lookback_days: int = 7
    iv_mult: float = 1.0             # implied vol = realised vol x iv_mult
    min_vol: float = 0.20
    # costs (verify against Delta India's current fee schedule)
    fee_rate: float = 0.0003         # fraction of underlying notional per leg trade
    fee_cap: float = 0.035           # ... capped at this fraction of the premium
    gst: float = 0.18                # GST on fees
    settlement_fee: bool = True      # charge the fee formula on ITM legs at expiry
    slippage_pct: float = 0.02       # fraction of option premium lost per leg trade
    min_slippage: float = 5.0        # USD per BTC per leg trade (half the spread on cheap options)


@dataclass
class Trade:
    strategy: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    expiry: pd.Timestamp
    spot_entry: float
    spot_exit: float
    vol: float
    legs: list[Leg]
    entry_premium: float     # net value per BTC at entry (negative = credit)
    exit_reason: str
    gross_pnl: float         # USD, before costs
    costs: float             # USD fees + slippage
    pnl: float = field(init=False)

    def __post_init__(self):
        self.pnl = self.gross_pnl - self.costs


def realised_vol(closes: pd.Series, bars_per_year: float) -> float:
    r = np.log(closes).diff().dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std() * math.sqrt(bars_per_year))


def _leg_cost(cfg: BacktestConfig, spot: float, price: float, settle: bool = False) -> float:
    """Fees + slippage in USD per BTC for one leg trade."""
    fee = min(cfg.fee_rate * spot, cfg.fee_cap * price) * (1 + cfg.gst)
    if settle:
        return fee
    return fee + max(cfg.slippage_pct * price, cfg.min_slippage)


def _value(legs: list[Leg], spot: float, t_years: float, vol: float) -> float:
    return sum(l.side * bs_price(l.kind, spot, l.strike, t_years, vol) for l in legs)


def run_backtest(candles: pd.DataFrame, strategy: Strategy, cfg: BacktestConfig) -> list[Trade]:
    """`candles`: DataFrame indexed by bar open time (UTC), columns open/high/low/close."""
    candles = candles.sort_index()
    bar = candles.index.to_series().diff().mode().iloc[0]
    bar_secs = bar.total_seconds()
    bars_per_year = SECONDS_PER_YEAR / bar_secs
    lookback = pd.Timedelta(days=cfg.vol_lookback_days)

    trades: list[Trade] = []
    day = candles.index[0].normalize() + lookback
    last_day = candles.index[-1].normalize()
    while day <= last_day:
        entry_time = day + pd.Timedelta(hours=cfg.entry_hour_utc)
        expiry = day + pd.Timedelta(hours=cfg.expiry_hour_utc)
        if expiry <= entry_time:
            expiry += pd.Timedelta(days=1)
        day += pd.Timedelta(days=1)

        if entry_time not in candles.index:
            continue
        path = candles.loc[entry_time: expiry - bar]
        if len(path) == 0 or path.index[-1] + bar != expiry:
            continue  # incomplete data for this trade

        history = candles.loc[entry_time - lookback: entry_time - bar]
        vol = max(realised_vol(history["close"], bars_per_year) * cfg.iv_mult, cfg.min_vol)
        if math.isnan(vol):
            continue
        spot0 = float(path["open"].iloc[0])
        t0 = (expiry - entry_time).total_seconds() / SECONDS_PER_YEAR
        ctx = EntryContext(entry_time, spot0, t0, vol, history, cfg.strike_step)
        legs = strategy.legs(ctx)
        if not legs:
            continue

        entry_prices = [bs_price(l.kind, spot0, l.strike, t0, vol) for l in legs]
        v0 = sum(l.side * p for l, p in zip(legs, entry_prices))
        basis = abs(v0)
        costs = sum(_leg_cost(cfg, spot0, p) for p in entry_prices)
        stop = -strategy.stop_mult * basis if strategy.stop_mult is not None else None
        target = strategy.take_profit * basis if strategy.take_profit is not None else None

        exit_reason, exit_time, exit_spot, exit_pnl = "expiry", expiry, None, None
        for ts, row in path.iterrows():
            t_end = max((expiry - (ts + bar)).total_seconds(), 0.0) / SECONDS_PER_YEAR
            t_start = (expiry - ts).total_seconds() / SECONDS_PER_YEAR
            if t_end <= 0:
                break  # last bar: settle below
            pnl_open = _value(legs, row["open"], t_start, vol) - v0
            pnl_hi = _value(legs, row["high"], t_end, vol) - v0
            pnl_lo = _value(legs, row["low"], t_end, vol) - v0
            worst, best = min(pnl_hi, pnl_lo), max(pnl_hi, pnl_lo)
            if stop is not None and (pnl_open <= stop or worst <= stop):
                exit_reason, exit_time = "stop", ts + bar
                exit_pnl = min(pnl_open, stop)  # gap through the stop fills at the open
                exit_spot = row["high"] if pnl_hi <= pnl_lo else row["low"]
                break
            if target is not None and (pnl_open >= target or best >= target):
                exit_reason, exit_time = "target", ts + bar
                exit_pnl = max(pnl_open, target)
                exit_spot = row["high"] if pnl_hi >= pnl_lo else row["low"]
                break

        if exit_reason == "expiry":
            exit_spot = float(path["close"].iloc[-1])
            settle = [intrinsic(l.kind, exit_spot, l.strike) for l in legs]
            exit_pnl = sum(l.side * s for l, s in zip(legs, settle)) - v0
            if cfg.settlement_fee:
                costs += sum(_leg_cost(cfg, exit_spot, s, settle=True) for s in settle if s > 0)
        else:
            t_exit = max((expiry - exit_time).total_seconds(), 0.0) / SECONDS_PER_YEAR
            costs += sum(_leg_cost(cfg, exit_spot, bs_price(l.kind, exit_spot, l.strike, t_exit, vol))
                         for l in legs)

        trades.append(Trade(strategy.name, entry_time, exit_time, expiry, spot0, float(exit_spot), vol,
                            legs, v0, exit_reason, exit_pnl * cfg.qty_btc, costs * cfg.qty_btc))
    return trades


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame([{
        "strategy": t.strategy, "entry_time": t.entry_time, "exit_time": t.exit_time,
        "spot_entry": t.spot_entry, "spot_exit": t.spot_exit, "vol": t.vol,
        "legs": " ".join(f"{'+' if l.side > 0 else '-'}{l.kind[0].upper()}{l.strike:.0f}" for l in t.legs),
        "entry_premium": t.entry_premium, "exit_reason": t.exit_reason,
        "gross_pnl": t.gross_pnl, "costs": t.costs, "pnl": t.pnl,
    } for t in trades])


def summarise(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"trades": 0}
    pnl = df["pnl"]
    equity = pnl.cumsum()
    dd = (equity - equity.cummax()).min()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    months = df.set_index("entry_time")["pnl"].resample("MS").sum()
    return {
        "trades": len(df),
        "net_pnl": round(pnl.sum(), 2),
        "costs": round(df["costs"].sum(), 2),
        "win_rate": round(len(wins) / len(df), 3),
        "avg_win": round(wins.mean(), 2) if len(wins) else 0.0,
        "avg_loss": round(losses.mean(), 2) if len(losses) else 0.0,
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else float("inf"),
        "max_drawdown": round(dd, 2),
        "worst_trade": round(pnl.min(), 2),
        "losing_months": f"{int((months < 0).sum())}/{len(months)}",
    }


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Month x strategy table of net PnL."""
    if df.empty:
        return pd.DataFrame()
    m = df.assign(month=df["entry_time"].dt.strftime("%Y-%m"))
    return m.pivot_table(index="month", columns="strategy", values="pnl", aggfunc="sum").round(0)
