"""Download and load candle data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .client import DeltaClient


def candles_to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"].astype(int), unit="s", utc=True)
    df = df.set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def download_candles(client: DeltaClient, symbol: str, resolution: str,
                     start: pd.Timestamp, end: pd.Timestamp, path: Path) -> pd.DataFrame:
    rows = client.get_candles(symbol, resolution, int(start.timestamp()), int(end.timestamp()))
    if not rows:
        raise RuntimeError(f"no candles returned for {symbol} {resolution} {start}..{end}")
    df = candles_to_frame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def load_candles(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()
