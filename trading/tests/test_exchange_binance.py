from decimal import Decimal
from django.conf import settings
from django.test import SimpleTestCase

from trading.exchanges import binance


class BinanceTestCase(SimpleTestCase):
    def test_buy_limit_order(self):
        exchange = binance.BinanceExchange(settings.TRADING_BINANCE_API_KEY, settings.TRADING_BINANCE_API_SECRET)
        exchange.place_buy_limit_order('BNBETH', Decimal('10000.0'), Decimal('0.00001'), test=True)
