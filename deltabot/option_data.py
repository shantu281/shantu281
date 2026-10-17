"""Historical BTC option chains from Delta Exchange India.

Delta keeps expired option contracts and serves their candles by symbol, for
example C-BTC-57000-270924 (traded price) and MARK:C-BTC-57000-270924 (mark
price). For each daily expiry we save the 5-minute candles of every call and
put whose strike is within a band around spot, one gzipped CSV per expiry:

    data/options/2025-05-10.csv.gz   columns: time, symbol, open, high, low, close
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from .client import DeltaAPIError, DeltaClient


def parse_symbol(symbol: str) -> tuple[str, str, float, pd.Timestamp]:
    """'C-BTC-57000-270924' -> ('call', 'BTC', 57000.0, Timestamp('2024-09-27 12:00 UTC'))."""
    side, underlying, strike, ddmmyy = symbol.split("-")
    kind = {"C": "call", "P": "put"}[side]
    expiry = pd.Timestamp(f"20{ddmmyy[4:6]}-{ddmmyy[2:4]}-{ddmmyy[0:2]} 12:00", tz="UTC")
    return kind, underlying, float(strike), expiry


def fetch_option_products(client: DeltaClient, underlying: str = "BTC") -> pd.DataFrame:
    """All expired and live options for `underlying` with their settlement time."""
    rows = []
    for state in ("expired", "live"):
        for p in client.get_products("call_options,put_options", states=state, underlying=underlying):
            if f"-{underlying}-" not in p["symbol"]:
                continue
            kind, _, strike, _ = parse_symbol(p["symbol"])
            rows.append({"symbol": p["symbol"], "product_id": p["id"], "kind": kind, "strike": strike,
                         "settlement_time": p.get("settlement_time"), "state": state})
    df = pd.DataFrame(rows)
    df["settlement_time"] = pd.to_datetime(df["settlement_time"], utc=True)
    return df


def _get_candles_retry(client: DeltaClient, symbol: str, start: int, end: int, resolution: str,
                       tries: int = 5) -> list[dict]:
    for i in range(tries):
        try:
            return client.get_candles(symbol, resolution, start, end)
        except (DeltaAPIError, OSError):  # rate limit / network: back off and retry
            if i == tries - 1:
                raise
            time.sleep(2 ** i + 1)
    return []


def download_expiry(client: DeltaClient, products: pd.DataFrame, expiry: pd.Timestamp, spot: float,
                    out_dir: Path, band: float = 0.05, hours_before: int = 26,
                    resolution: str = "5m", price: str = "mark", workers: int = 4) -> Path | None:
    """Download one expiry's chain (strikes within spot x (1 +/- band)). Skips if already saved."""
    out = out_dir / f"{expiry:%Y-%m-%d}.csv.gz"
    if out.exists():
        return out
    chain = products[(products["settlement_time"] == expiry)
                     & (products["strike"].between(spot * (1 - band), spot * (1 + band)))]
    if chain.empty:
        return None
    start = int((expiry - pd.Timedelta(hours=hours_before)).timestamp())
    end = int(expiry.timestamp())
    prefix = "MARK:" if price == "mark" else ""

    def one(sym):
        rows = _get_candles_retry(client, prefix + sym, start, end, resolution)
        return [{"time": int(r["time"]), "symbol": sym, "open": r["open"], "high": r["high"],
                 "low": r["low"], "close": r["close"]} for r in rows]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [r for chunk in pool.map(one, chain["symbol"]) for r in chunk]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    df.sort_values(["symbol", "time"]).to_csv(tmp, index=False, compression="gzip")
    tmp.replace(out)  # only complete files count as done, so an interrupted run resumes cleanly
    return out


def load_chain(path: str | Path) -> dict[tuple[str, float], pd.DataFrame]:
    """{(kind, strike): OHLC frame indexed by bar open time}."""
    df = pd.read_csv(path, compression="gzip")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    chain = {}
    for sym, g in df.groupby("symbol"):
        kind, _, strike, _ = parse_symbol(sym)
        chain[(kind, strike)] = g.set_index("time")[["open", "high", "low", "close"]].astype(float).sort_index()
    return chain
