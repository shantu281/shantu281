"""Position sizing and the monthly loss stop used for live/paper trading.

Tested on the iron butterfly with $500 fresh each month (research/ifly_boost.py notes in HANDOFF.md):
stopping for the rest of the month once the month is down 10% cut the worst month from -$144 to -$75
and raised the 26-month total from +$681 to +$787.
"""

from __future__ import annotations

from dataclasses import dataclass


def size_lots(balance: float, margin_per_lot: float, max_loss_per_lot: float | None = None,
              risk_fraction: float | None = None) -> int:
    """Whole lots that fit the margin, and optionally keep the capped loss within risk_fraction of balance."""
    if balance <= 0 or margin_per_lot <= 0:
        return 0
    lots = int(balance // margin_per_lot)
    if risk_fraction is not None and max_loss_per_lot:
        lots = min(lots, int(risk_fraction * balance // max_loss_per_lot))
    return max(lots, 0)


@dataclass
class MonthlyStop:
    """No new trades for the rest of the calendar month once the month is down `stop_fraction`."""
    stop_fraction: float = 0.10
    month: str | None = None
    start_balance: float = 0.0

    def allowed(self, month: str, balance: float) -> bool:
        """`month` like '2026-10'. Call before each new trade with the current balance."""
        if month != self.month:
            self.month, self.start_balance = month, balance
        return balance > self.start_balance * (1 - self.stop_fraction)
