from money_dahong.settings import Settings


def test_live_trading_enabled_requires_yes() -> None:
    settings = Settings(
        TRADING_MODE="live",
        CONFIRM_LIVE_TRADING="",
    )
    assert settings.live_trading_enabled() is False

    settings = Settings(
        TRADING_MODE="live",
        CONFIRM_LIVE_TRADING="YES",
    )
    assert settings.live_trading_enabled() is True

