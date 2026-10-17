import pandas as pd

from deltabot.option_data import download_expiry, load_chain


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_candles(self, symbol, resolution, start, end):
        self.calls.append(symbol)
        return [{"time": start + i * 300, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i}
                for i in range(3)]


def test_download_expiry_band_mark_prefix_and_resume(tmp_path):
    expiry = pd.Timestamp("2025-05-10 12:00", tz="UTC")
    products = pd.DataFrame({
        "symbol": ["C-BTC-95000-100525", "P-BTC-95000-100525", "C-BTC-120000-100525", "C-BTC-95000-110525"],
        "kind": ["call", "put", "call", "call"],
        "strike": [95000.0, 95000.0, 120000.0, 95000.0],
        "settlement_time": [expiry, expiry, expiry, expiry + pd.Timedelta(days=1)],
    })
    client = FakeClient()
    path = download_expiry(client, products, expiry, 95_000, tmp_path, band=0.05, workers=1)
    assert sorted(client.calls) == ["MARK:C-BTC-95000-100525", "MARK:P-BTC-95000-100525"]
    chain = load_chain(path)
    assert set(chain) == {("call", 95000.0), ("put", 95000.0)}
    assert len(chain[("call", 95000.0)]) == 3

    client.calls.clear()
    download_expiry(client, products, expiry, 95_000, tmp_path, band=0.05, workers=1)
    assert client.calls == []  # already downloaded: skipped
