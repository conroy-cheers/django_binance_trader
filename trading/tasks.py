import logging
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from django.conf import settings

from trading.enums import OrderSide, OrderState
from trading.exchanges import binance
from trading.models import LimitOrder

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=AbortableTask)
def trade_symbol(self, symbol: str):
    binance_exchange = binance.BinanceExchange(
        settings.TRADING_BINANCE_API_KEY, settings.TRADING_BINANCE_API_SECRET)

    while True:
        # # Do stuff here
        # # TODO If the price goes down, buy some stuff
        # if True:
        #     # Create order
        #     order = LimitOrder(symbol=symbol, side=OrderSide.BUY, price=0.0001, quantity=10000)
        #     # Place order
        #     order.place(binance_exchange)
        #     # Wait for order to complete
        #     order.block_until_complete_or_timeout(binance_exchange)
        #
        #     # Check order status
        #     if order.status == OrderState.COMPLETED or order.status == OrderState.CANCELLED_PARTIAL:
        #         # TODO Sell things incl. stop loss
        #         pass
        #     elif order.status == OrderState.CANCELLED:
        #         # Go back to the beginning
        #         continue
        #     else:
        #         # Something went wrong - the order hasn't been cancelled
        #         logger.error("Something went wrong with %s order %s. Exiting.", order.symbol, order.exchange_order_id)
        #         raise Exception

        # Check if aborted
        if self.is_aborted():
            return
