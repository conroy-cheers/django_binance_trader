import datetime
import logging
import time
from django.db import models
from django.core.exceptions import ValidationError

from trading.enums import OrderState, OrderSide, ORDER_STATE_TERMINAL_VALUES
from trading.exchanges.exchange_base import Exchange

logger = logging.getLogger(__name__)


class TradingSession(models.Model):
    """
    Represents a trading session.
    """
    time_opened = models.DateTimeField(null=True, help_text="The time at which the session was opened.",
                                       auto_now_add=True)
    symbol = models.CharField(max_length=10, help_text="Symbol, e.g. \"BNBBTC\"")
    time_closed = models.DateTimeField(null=True, help_text="The time at which the session was closed.")

    # Non-persistent field
    _exchange = None

    # Getter and setter to make self.exchange readonly past initial set
    @property
    def exchange(self):
        return self._exchange

    @exchange.setter
    def exchange(self, value):
        if self._exchange is not None:
            raise ValueError("TradingSession.exchange should only be set once. "
                             "Try creating using TradingSession.open(exchange, symbol).")
        self._exchange = value

    @classmethod
    def open(cls, exchange: Exchange, symbol: str):
        """
        Creates and saves a TradingSession with a provided Exchange and symbol.
        :param exchange: Exchange to trade on.
        :param symbol: Symbol to trade.
        :return: Created TradingSession instance.
        """
        # Create TradingSession with provided exchange and symbol
        session = cls(symbol=symbol)
        session.save()

        session.exchange = exchange

        # Return created session
        return session


class ActiveOrderManager(models.Manager):
    def get_queryset(self):
        return super(ActiveOrderManager, self).get_queryset().filter(status__in=ORDER_STATE_TERMINAL_VALUES)


class OrderBase(models.Model):
    """
    Base class for orders.
    """
    trading_session = models.ForeignKey(TradingSession, null=False, on_delete=models.CASCADE,
                                        help_text="The trading session under which this order was placed.")

    time_placed = models.DateTimeField(null=True, help_text="The time at which the order was placed.")
    side = models.PositiveSmallIntegerField(choices=[
        (OrderSide.BUY, 'Buy'),
        (OrderSide.SELL, 'Sell')
    ])
    quantity = models.DecimalField(decimal_places=10, max_digits=20, help_text="Quantity of the symbol to buy/sell.")
    quantity_filled = models.DecimalField(decimal_places=10, max_digits=20,
                                          help_text="Quantity of the order that has filled.", blank=True, null=True)
    status = models.PositiveSmallIntegerField(choices=[
        (OrderState.PENDING, 'Pending'),
        (OrderState.PLACED, 'Placed'),
        (OrderState.FILLING, 'Filling'),
        (OrderState.COMPLETED, 'Completed'),
        (OrderState.CANCELLED, 'Cancelled'),
        (OrderState.CANCELLED_PARTIAL, 'Partially cancelled')
    ], default=OrderState.PENDING)
    time_closed = models.DateTimeField(null=True, help_text="The time at which the order was closed.")

    exchange_order_id = models.CharField(max_length=255, help_text="Order ID string obtained from exchange.")

    active_objects = ActiveOrderManager()

    @property
    def symbol(self):
        return self.trading_session.symbol

    class Meta:
        abstract = True

    def save(self, **kwargs):
        """
        Override model save method. Prevents an order that was previously closed, then modified, from being saved.
        Automatically sets time_closed if the order is being closed.
        """
        if not self.pk:
            # First save. Do nothing special
            super(OrderBase, self).save(**kwargs)
        else:
            # This is an edit operation. Get old self
            old_self = type(self).objects.get(pk=self.pk)

            # Ensure that we aren't editing a closed order
            if old_self.is_closed:
                raise ValidationError("Saving an edited closed order is not allowed.")

            # Check if the order is being closed
            if not old_self.is_closed and self.is_closed:
                # Set time_closed to current
                self.time_closed = datetime.datetime.now()

            # Now save as usual.
            super(OrderBase, self).save(**kwargs)

    @property
    def is_closed(self):
        """
        Checks if the order is completed (either completed or cancelled).
        :return: True if order is completed, False otherwise.
        """
        return self.status in ORDER_STATE_TERMINAL_VALUES

    def place(self, exchange: Exchange):
        """
        Places order with exchange.
        :param exchange: Instance subclassing Exchange to place the order with.
        """
        raise NotImplementedError

    def cancel(self, exchange: Exchange):
        """
        Cancels the order.
        :param exchange: Instance subclassing Exchange to cancel the order with.
        """
        if self.is_closed:
            raise ValidationError("Cannot cancel an already completed order.")

        exchange.cancel_order(self.symbol, self.exchange_order_id)
        self.update_from_exchange(exchange)

    def block_until_complete_or_timeout(self, exchange: Exchange, timeout: float = 0.5):
        """
        Blocks until either the order is completed. If the timeout is reached and the order is not filled,
        cancels the order.
        :param exchange: Exchange to check with.
        :param timeout: Time after which order will be cancelled.
        """
        start_time = time.time()
        while True:
            # Update info
            self.update_from_exchange(exchange)

            action_name = ("Buy", "Sell")[self.side]

            # Check if complete
            if self.status == OrderState.FILLING:
                logger.info("%s of %s %s partially filled: %s / %s", action_name, self.quantity, self.symbol,
                            str(self.quantity_filled),
                            str(self.quantity))
            elif self.status == OrderState.COMPLETED:
                logger.info("%s of %s %s filled: %s", action_name, self.quantity, self.symbol,
                            str(self.quantity_filled))
                # Order filled. Return now
                return

            duration = time.time() - start_time
            if duration > timeout:
                logger.warning("%s of %s %s timed out after %0.2f seconds", action_name, self.quantity, self.symbol,
                               duration)
                self.cancel(exchange)
                logger.info("%s cancelled", action_name)
                return

            time.sleep(0.1)

    def update_from_exchange(self, exchange: Exchange):
        """
        Updates order status and fill state from the exchange.
        :param exchange: Instance subclassing Exchange to check status with.
        """
        if self.is_closed:
            logger.warning("Updating an already completed order.")

        new_status = exchange.get_order_status(self.symbol, self.exchange_order_id, OrderState(self.status))
        self.status = new_status.status
        self.quantity_filled = new_status.quantity_filled


class MarketOrder(OrderBase):
    """
    Represents a buy/sell order at market price.
    """

    def place(self, exchange: Exchange):
        """
        Places order with exchange.
        :param exchange: Instance subclassing Exchange to place the order with.
        """
        if self.is_closed:
            raise ValidationError("Cannot place an already completed order.")

        if self.side == OrderSide.BUY:
            # Place buy order
            self.exchange_order_id = exchange.place_buy_market_order(self.symbol, self.quantity)
        elif self.side == OrderSide.SELL:
            # Place sell order
            self.exchange_order_id = exchange.place_sell_market_order(self.symbol, self.quantity)
        else:
            raise ValidationError
        # If command succeeded, update status
        self.status = OrderState.PLACED
        self.time_placed = datetime.datetime.now()

        # Save to database
        self.save()


class LimitOrder(OrderBase):
    """
    Represents a buy/sell limit order.
    """
    price = models.DecimalField(decimal_places=10, max_digits=20,
                                help_text="Limit price to buy below (for buy orders) or sell above (for sell orders).")

    def place(self, exchange: Exchange):
        """
        Places order with exchange.
        :param exchange: Instance subclassing Exchange to place the order with.
        :return:
        """
        if self.is_closed:
            raise ValidationError("Cannot place an already completed order.")

        if self.side == OrderSide.BUY:
            # Place buy order
            exchange.place_buy_limit_order(self.symbol, self.quantity, self.price)
            # If command succeeded, update status
            self.status = OrderState.PLACED
        elif self.side == OrderSide.SELL:
            # Place sell order
            exchange.place_sell_limit_order(self.symbol, self.quantity, self.price)
            # If command succeeded, update status
            self.status = OrderState.PLACED
