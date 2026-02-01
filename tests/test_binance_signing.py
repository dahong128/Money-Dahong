import hmac
from hashlib import sha256

from money_dahong.exchange.binance_spot import build_query_string, sign_query_string


def test_build_query_string_sorts_keys() -> None:
    assert build_query_string({"b": 2, "a": 1}) == "a=1&b=2"


def test_sign_query_string_matches_known_example() -> None:
    qs = (
        "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&"
        "recvWindow=5000&timestamp=1499827319559"
    )
    secret = "NhqPtmdSJY7tT3x5XJ"
    expected = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), sha256).hexdigest()
    assert sign_query_string(qs, secret) == expected
