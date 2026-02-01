from decimal import Decimal

from money_dahong.engine.trader import _extract_balance


def test_extract_balance_returns_free_and_locked() -> None:
    account = {
        "balances": [
            {"asset": "USDT", "free": "12.34", "locked": "5"},
            {"asset": "ETH", "free": "0.5", "locked": "0.1"},
        ]
    }
    free, locked = _extract_balance(account=account, asset="USDT")
    assert free == Decimal("12.34")
    assert locked == Decimal("5")


def test_extract_balance_missing_asset_returns_zeroes() -> None:
    account = {"balances": [{"asset": "BTC", "free": "1", "locked": "0"}]}
    free, locked = _extract_balance(account=account, asset="USDT")
    assert free == Decimal("0")
    assert locked == Decimal("0")

