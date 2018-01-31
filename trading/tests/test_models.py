from django.utils import timezone
from django.core.exceptions import ValidationError
from django.test import TestCase

from trading.exchanges.exchange_base import Exchange
from trading.models import TradingSession


class TestTradingSession(TestCase):
    def test_open(self):
        new_trading_session = TradingSession.open(Exchange(), "BNBBTC")
        # Assert that the opening time is correct
        self.assertAlmostEqual((timezone.now() - new_trading_session.time_opened).total_seconds(), 0, places=2)
        # Assert that the session reads as open
        self.assertTrue(new_trading_session.is_open)

    def test_close(self):
        new_trading_session = TradingSession(symbol="BNBBTC")
        new_trading_session.close()
        # Assert that the closing time is correct
        self.assertAlmostEqual((timezone.now() - new_trading_session.time_closed).total_seconds(), 0, places=2)
        # Assert that the session reads as closed
        self.assertFalse(new_trading_session.is_open)

    def test_disallow_edit_closed_session(self):
        session = TradingSession(symbol="BNBBTC")
        session.close()
        with self.assertRaises(ValidationError):
            session.symbol = "SOMETHING"
            session.save()

    def test_disallow_edit_exchange(self):
        session = TradingSession.open(Exchange(), "BNBBTC")
        with self.assertRaises(ValidationError):
            session.exchange = Exchange()
