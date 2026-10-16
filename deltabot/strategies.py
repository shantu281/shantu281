"""Candidate BTC option strategies for the backtest.

Each strategy decides the legs to open at entry time and its own exit rules.
Exit thresholds are expressed relative to the entry premium:
  - short-premium (credit) trades: stop when the loss reaches `stop_mult` x credit,
    take profit when `take_profit` (fraction) of the credit has been captured.
  - long-premium (debit) trades: stop when `stop_mult` (fraction) of the debit is lost,
    take profit when the gain reaches `take_profit` x debit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .pricing import round_strike, strike_for_delta


@dataclass(frozen=True)
class Leg:
    kind: str      # "call" or "put"
    strike: float
    side: int      # +1 long, -1 short


@dataclass
class EntryContext:
    time: pd.Timestamp
    spot: float
    t_years: float          # time to expiry
    vol: float              # annualised vol used for pricing / strike selection
    history: pd.DataFrame   # candles strictly before entry
    strike_step: float


@dataclass
class Strategy:
    name: str
    stop_mult: float | None = None
    take_profit: float | None = None
    params: dict = field(default_factory=dict)

    def legs(self, ctx: EntryContext) -> list[Leg]:
        raise NotImplementedError


class ShortStraddle(Strategy):
    def legs(self, ctx):
        k = round_strike(ctx.spot, ctx.strike_step)
        return [Leg("call", k, -1), Leg("put", k, -1)]


class ShortStrangle(Strategy):
    def legs(self, ctx):
        d = self.params.get("delta", 0.20)
        kc = strike_for_delta("call", ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        kp = strike_for_delta("put", ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        return [Leg("call", kc, -1), Leg("put", kp, -1)]


class IronCondor(Strategy):
    def legs(self, ctx):
        ds, dw = self.params.get("short_delta", 0.20), self.params.get("wing_delta", 0.05)
        args = (ctx.t_years, ctx.vol, ctx.strike_step)
        sc = strike_for_delta("call", ctx.spot, ds, *args)
        sp = strike_for_delta("put", ctx.spot, ds, *args)
        lc = max(strike_for_delta("call", ctx.spot, dw, *args), sc + ctx.strike_step)
        lp = min(strike_for_delta("put", ctx.spot, dw, *args), sp - ctx.strike_step)
        return [Leg("call", sc, -1), Leg("put", sp, -1), Leg("call", lc, +1), Leg("put", lp, +1)]


class LongStraddle(Strategy):
    def legs(self, ctx):
        k = round_strike(ctx.spot, ctx.strike_step)
        return [Leg("call", k, +1), Leg("put", k, +1)]


class TrendBuy(Strategy):
    """Buy a call in an uptrend / a put in a downtrend (EMA fast vs slow on the history candles)."""

    def legs(self, ctx):
        fast, slow = self.params.get("fast", 20), self.params.get("slow", 50)
        closes = ctx.history["close"]
        if len(closes) < slow:
            return []
        ema_f = closes.ewm(span=fast, adjust=False).mean().iloc[-1]
        ema_s = closes.ewm(span=slow, adjust=False).mean().iloc[-1]
        last = closes.iloc[-1]
        d = self.params.get("delta", 0.40)
        if last > ema_f > ema_s:
            kind = "call"
        elif last < ema_f < ema_s:
            kind = "put"
        else:
            return []
        k = strike_for_delta(kind, ctx.spot, d, ctx.t_years, ctx.vol, ctx.strike_step)
        return [Leg(kind, k, +1)]


def default_strategies() -> list[Strategy]:
    """The starting set to compare. Tune or add variants here."""
    return [
        ShortStraddle("short_straddle", stop_mult=1.0, take_profit=0.5),
        ShortStraddle("short_straddle_noexit"),
        ShortStrangle("short_strangle_d20", stop_mult=1.5, take_profit=0.6, params={"delta": 0.20}),
        ShortStrangle("short_strangle_d10", stop_mult=2.0, take_profit=0.7, params={"delta": 0.10}),
        IronCondor("iron_condor_20_05", stop_mult=1.5, take_profit=0.6,
                   params={"short_delta": 0.20, "wing_delta": 0.05}),
        LongStraddle("long_straddle", stop_mult=0.5, take_profit=1.0),
        TrendBuy("trend_buy_d40", stop_mult=0.5, take_profit=1.5, params={"delta": 0.40}),
    ]
