"""Minimal REST client for Delta Exchange India (v2 API).

Public endpoints need no key. Private endpoints are signed with HMAC-SHA256 over
    method + timestamp + path + query_string + body
as described in the Delta Exchange API docs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

import requests

INDIA_BASE_URL = "https://api.india.delta.exchange"
INDIA_TESTNET_URL = "https://cdn-ind.testnet.deltaex.org"

MAX_CANDLES_PER_REQUEST = 2000

RESOLUTION_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "1d": 86400,
}


class DeltaAPIError(RuntimeError):
    pass


def sign(secret: str, method: str, timestamp: str, path: str, query: str = "", body: str = "") -> str:
    """HMAC-SHA256 signature. `query` must include the leading '?' when non-empty."""
    message = method.upper() + timestamp + path + query + body
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class DeltaClient:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 base_url: str = INDIA_BASE_URL, timeout: float = 15.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "deltabot/0.1", "Content-Type": "application/json"})

    # ---- transport -------------------------------------------------------

    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None, auth: bool = False) -> Any:
        query = "?" + urlencode(params) if params else ""
        payload = json.dumps(body, separators=(",", ":")) if body else ""
        headers = {}
        if auth:
            if not (self.api_key and self.api_secret):
                raise DeltaAPIError("API key and secret are required for private endpoints")
            ts = str(int(time.time()))
            headers.update({
                "api-key": self.api_key,
                "timestamp": ts,
                "signature": sign(self.api_secret, method, ts, path, query, payload),
            })
        resp = self.session.request(method, self.base_url + path + query, data=payload or None,
                                    headers=headers, timeout=self.timeout)
        try:
            data = resp.json()
        except ValueError:
            raise DeltaAPIError(f"{method} {path}: HTTP {resp.status_code}: {resp.text[:200]}")
        if not resp.ok or not data.get("success", False):
            raise DeltaAPIError(f"{method} {path}: HTTP {resp.status_code}: {data.get('error', data)}")
        return data.get("result")

    # ---- public market data ---------------------------------------------

    def get_products(self, contract_types: str | None = None, states: str | None = None,
                     underlying: str | None = None, page_size: int = 500) -> list[dict]:
        """All products, following pagination. contract_types e.g. 'call_options,put_options'."""
        out, after = [], None
        while True:
            params = {"page_size": page_size}
            if contract_types:
                params["contract_types"] = contract_types
            if states:
                params["states"] = states
            if underlying:
                params["underlying_asset_symbols"] = underlying
            if after:
                params["after"] = after
            resp = self.session.get(self.base_url + "/v2/products", params=params, timeout=self.timeout)
            data = resp.json()
            if not data.get("success", False):
                raise DeltaAPIError(f"/v2/products: {data.get('error', data)}")
            out.extend(data["result"])
            after = (data.get("meta") or {}).get("after")
            if not after:
                return out

    def get_tickers(self, contract_types: str = "call_options,put_options",
                    underlying: str = "BTC") -> list[dict]:
        return self._request("GET", "/v2/tickers",
                             {"contract_types": contract_types, "underlying_asset_symbols": underlying})

    def get_ticker(self, symbol: str) -> dict:
        return self._request("GET", f"/v2/tickers/{symbol}")

    def get_candles(self, symbol: str, resolution: str, start: int, end: int) -> list[dict]:
        """OHLCV candles between unix-second timestamps, paginated, sorted oldest first.

        Use symbol 'BTCUSD' for the perpetual, 'MARK:<symbol>' for mark price and
        e.g. '.DEXBTUSD' for the BTC index.
        """
        step = RESOLUTION_SECONDS[resolution] * MAX_CANDLES_PER_REQUEST
        rows: dict[int, dict] = {}
        t = start
        while t < end:
            chunk_end = min(t + step, end)
            result = self._request("GET", "/v2/history/candles",
                                   {"resolution": resolution, "symbol": symbol,
                                    "start": t, "end": chunk_end})
            for c in result or []:
                rows[int(c["time"])] = c
            t = chunk_end
        return [rows[k] for k in sorted(rows)]

    # ---- private: account & orders (used by the live/paper runner later) --

    def get_balances(self) -> list[dict]:
        return self._request("GET", "/v2/wallet/balances", auth=True)

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions/margined", auth=True)

    def place_order(self, product_id: int, side: str, size: int, order_type: str = "market_order",
                    limit_price: float | None = None, reduce_only: bool = False,
                    client_order_id: str | None = None) -> dict:
        body: dict[str, Any] = {"product_id": product_id, "side": side, "size": size,
                                "order_type": order_type, "reduce_only": reduce_only}
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/v2/orders", body=body, auth=True)

    def cancel_order(self, order_id: int, product_id: int) -> dict:
        return self._request("DELETE", "/v2/orders", body={"id": order_id, "product_id": product_id}, auth=True)
