import logging
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from django.conf import settings

from trading.enums import OrderSide, OrderState
from trading.exchanges import binance
from trading.models import Order, TradingSession, BuySellPair

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=AbortableTask)
def trade_symbol(self, symbol: str):
    """
    INCOMPLETE - USE AT YOUR OWN PERIL!!!
    Makes (hopefully) profitable trades on a specified symbol.
    """
    binance_exchange = binance.BinanceExchange(
        settings.TRADING_BINANCE_API_KEY, settings.TRADING_BINANCE_API_SECRET)

    # TODO resume an open session from the database with the same symbol if available
    # Open trading session
    session = TradingSession.open(binance_exchange, symbol)

    while True:
        # TODO actually get prices
        price = 0.0001
        # TODO actually get quantities
        quantity = 10000000000
        if True:  # TODO If the price goes down, buy some stuff
            # Create a buy/sell pair
            buy_order = Order(trading_session=session, side=OrderSide.BUY, price=price, quantity=quantity)
            pair = BuySellPair.open(session, buy_order)

            # Place the opening order
            pair.opening_order.place_limit(binance_exchange)
            # Wait for order to complete
            pair.opening_order.block_until_complete_or_timeout(binance_exchange)

            # Check order status
            if pair.opening_order.status in (OrderState.COMPLETED, OrderState.CANCELLED_PARTIAL):
                # Create a sell
                # TODO actually calculate sell price properly
                sell_order = Order(trading_session=session, side=OrderSide.SELL, price=price, quantity=quantity)
                pair.close(sell_order)
                # TODO implement stop limit
                pair.closing_order.place_limit(binance_exchange)
                # Wait for order to complete
                pair.closing_order.block_until_complete_or_timeout(binance_exchange, timeout=30)
            elif pair.opening_order.status == OrderState.CANCELLED:
                # Go back to the beginning
                continue
            else:
                # Something went wrong - the order hasn't been cancelled
                logger.error("Something went wrong with %s order %s. Exiting.",
                             pair.opening_order.symbol, pair.opening_order.exchange_order_id)
                raise Exception

        # Check if aborted
        if self.is_aborted():
            return
