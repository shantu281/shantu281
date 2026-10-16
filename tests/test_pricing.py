import math

import pytest

from deltabot.pricing import bs_delta, bs_price, strike_for_delta


def test_known_value():
    # S=K=100, T=1, vol=20%, r=0 -> ATM call = 7.9656
    assert bs_price("call", 100, 100, 1.0, 0.2) == pytest.approx(7.9656, abs=1e-4)


@pytest.mark.parametrize("k", [50_000, 60_000, 70_000])
def test_put_call_parity(k):
    s, t, v = 60_000, 1 / 365, 0.5
    assert bs_price("call", s, k, t, v) - bs_price("put", s, k, t, v) == pytest.approx(s - k, abs=1e-6)


def test_expiry_is_intrinsic():
    assert bs_price("call", 61_000, 60_000, 0, 0.5) == 1_000
    assert bs_price("put", 61_000, 60_000, 0, 0.5) == 0


def test_strike_for_delta():
    s, t, v = 60_000, 1 / 365, 0.5
    kc = strike_for_delta("call", s, 0.2, t, v, 200)
    kp = strike_for_delta("put", s, 0.2, t, v, 200)
    assert kc > s > kp
    assert abs(bs_delta("call", s, kc, t, v)) == pytest.approx(0.2, abs=0.03)
    assert abs(bs_delta("put", s, kp, t, v)) == pytest.approx(0.2, abs=0.03)
