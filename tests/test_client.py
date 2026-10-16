import hashlib
import hmac

from deltabot.client import sign


def test_signature_message_order():
    expected = hmac.new(b"secret", b"GET1700000000/v2/orders?product_id=1", hashlib.sha256).hexdigest()
    assert sign("secret", "get", "1700000000", "/v2/orders", "?product_id=1") == expected
