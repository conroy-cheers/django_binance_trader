import logging
import time
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from trading.enums import OrderState, OrderSide, ORDER_STATE_TERMINAL_VALUES
from trading.exchanges.exchange_base import Exchange

logger = logging.getLogger(__name__)


class TradingSessionManager(models.Manager):
    """
    Manager for TradingSession.
    Prefetches related orders for improved performance.
    """

    def get_queryset(self):
        return super(TradingSessionManager, self).get_queryset().prefetch_related('order_set')


class ActiveTradingSessionManager(models.Manager):
    """
    Manager for TradingSession.
    Only returns active sessions. Also prefetches related orders.
    """

    def get_queryset(self):
        return super(ActiveTradingSessionManager, self).get_queryset().filter(
            time_closed__isnull=True).prefetch_related('order_set')


class TradingSession(models.Model):
    """
    Represents a trading session.
    """
    time_opened = models.DateTimeField(null=True, help_text="The time at which the session was opened.",
                                       auto_now_add=True)
    symbol = models.CharField(max_length=10, help_text="Symbol, e.g. \"BNBBTC\"")
    time_closed = models.DateTimeField(null=True, help_text="The time at which the session was closed.")

    # Non-persistent field
    _exchange = None  # TODO represent different exchanges as ORM models

    # Managers
    objects = TradingSessionManager()
    active_objects = ActiveTradingSessionManager()

    def save(self, **kwargs):
        """
        Override model save method. Prevents a session that was previously closed, then modified, from being saved.
        """
        if self.pk:
            # This is an edit operation. Get old self
            old_self = type(self).objects.get(pk=self.pk)

            # Ensure that we aren't editing a closed order
            if not old_self.is_open:
                raise ValidationError("Saving an edited closed session is not allowed.")

        super(TradingSession, self).save(**kwargs)

    @property
    def is_open(self):
        """
        Checks if the session is open.
        :return: True if session is open, False otherwise.
        """
        return self.time_closed is None

    # Getter and setter to make self.exchange readonly past initial set
    @property
    def exchange(self):
        return self._exchange

    @exchange.setter
    def exchange(self, value):
        if self._exchange is not None:
            raise ValidationError("TradingSession.exchange should only be set once. "
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

    def close(self):
        """
        Closes the trading session (permanently).
        """
        self.time_closed = timezone.now()
        self.save()


class BuySellPair(models.Model):
    """
    Represents a balanced buy and sell of the same amount on the same symbol.
    """
    trading_session = models.ForeignKey(TradingSession, null=False, on_delete=models.CASCADE,
                                        related_name="buy_sell_pairs",
                                        help_text="The trading session under which this pair was traded.")

    _first_order = models.OneToOneField('Order', on_delete=models.CASCADE, null=False,
                                        related_name="buy_sell_pair_first",
                                        help_text="The buy/sell that opens this pair.")
    _second_order = models.OneToOneField('Order', on_delete=models.CASCADE, null=True,
                                         related_name="buy_sell_pair_second",
                                         help_text="The opposing buy/sell that closes this pair.")

    @property
    def opening_order(self):
        return self._first_order

    @property
    def closing_order(self):
        return self._second_order

    @classmethod
    def open(cls, session: TradingSession, order: 'Order') -> 'BuySellPair':
        """
        Creates and saves a BuySellPair with a provided TradingSession and opening order. Provided opening order
        must not have been placed with exchange. Does not place the provided order; this must be done afterwards.
        :param session: Session to create pair on. Must be an open session.
        :param order: Opening order to store. Must not have already been placed with exchange.
        :return: Created BuySellPair instance.
        """
        # Ensure that provided session is open
        if not session.is_open:
            raise ValidationError(
                "New buy/sell pairs (and new orders) cannot be associated with a closed TradingSession.")
        # Ensure that provided order is unplaced (i.e. status PENDING)
        if order.status != OrderState.PENDING:
            raise ValidationError("New buy/sell pairs cannot be created with an already placed order.")

        # Create with provided session and order
        session = cls()
        session.trading_session = session
        session._first_order = order
        session.save()

        # Return created session
        return session

    def close(self, order: 'Order'):
        """
        Sets the second order, ensuring that:

        * the first order has been completed

        * its side is opposite to the first order's

        * it has not yet been placed with the exchange.
        """
        if self._first_order.status is OrderState.CANCELLED:
            raise ValidationError("Cannot set a second order because the first order was cancelled without filling.")
        if not self._first_order.is_closed:
            raise ValidationError("Cannot set a second order before the first order is closed.")
        if order.is_closed:
            raise ValidationError("Cannot set a second order that is closed.")
        if self._first_order.side == order.side:
            raise ValidationError(f"Cannot complete this buy/sell pair with a {OrderSide(order.side).name},"
                                  f"as its first order was a {OrderSide(self._first_order.side).name}.")

        # Set the second order
        self._second_order = order

    @property
    def is_closed(self):
        """
        Determines whether the order pair is completed.
        """
        if self._first_order.status in (OrderState.COMPLETED, OrderState.CANCELLED_PARTIAL):
            # Second order is required if first order completed
            if self._second_order.is_closed:
                return True
        elif self._first_order.status is OrderState.CANCELLED:
            # If first order was cancelled without filling, second order can be None
            return True
        else:
            return False

    def profit(self) -> Decimal:
        """
        The gross profit made on this pair of orders, expressed as a decimal (e.g. 0.008 means 0.8% profit).
        Does not include fees.
        """
        # TODO include fees
        if self.is_closed:
            return self._second_order.quantity_filled * self._second_order.price / \
                   self._first_order.quantity_filled * self._first_order.price - 1


class ActiveOrderManager(models.Manager):
    def get_queryset(self):
        return super(ActiveOrderManager, self).get_queryset().filter(status__in=ORDER_STATE_TERMINAL_VALUES)


class Order(models.Model):
    """
    Base model for orders.
    """
    trading_session = models.ForeignKey(TradingSession, null=False, on_delete=models.CASCADE,
                                        help_text="The trading session under which this order was placed.")

    time_placed = models.DateTimeField(null=True, help_text="The time at which the order was placed.")
    side = models.PositiveSmallIntegerField(choices=[
        (OrderSide.BUY, 'Buy'),
        (OrderSide.SELL, 'Sell')
    ])
    price = models.DecimalField(decimal_places=10, max_digits=20, null=True,
                                help_text="Limit price to buy below (for buy orders) or sell above (for sell orders).")
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

    def save(self, **kwargs):
        """
        Override model save method. Prevents an order that was previously closed, then modified, from being saved.
        Automatically sets time_closed if the order is being closed.
        """
        if not self.pk:
            # First save. Do nothing special
            super(Order, self).save(**kwargs)
        else:
            # This is an edit operation. Get old self
            old_self = type(self).objects.get(pk=self.pk)

            # Ensure that we aren't editing a closed order
            if old_self.is_closed:
                raise ValidationError("Saving an edited closed order is not allowed.")

            # Check if the order is being closed
            if not old_self.is_closed and self.is_closed:
                # Set time_closed to current
                self.time_closed = timezone.now()

            # Now save as usual.
            super(Order, self).save(**kwargs)

    @property
    def is_closed(self):
        """
        Checks if the order is completed (either completed or cancelled).
        :return: True if order is completed, False otherwise.
        """
        return self.status in ORDER_STATE_TERMINAL_VALUES

    def place_limit(self, exchange: Exchange):
        """
        Places limit order with exchange.
        :param exchange: Instance subclassing Exchange to place the order with.
        """
        if self.is_closed:
            raise ValidationError("Cannot place an already completed order.")
        if self.price is None:
            raise ValidationError("Price must be set to place a limit order.")

        if self.side == OrderSide.BUY:
            # Place buy order
            self.exchange_order_id = exchange.place_buy_limit_order(self.symbol, self.quantity, self.price)
        elif self.side == OrderSide.SELL:
            # Place sell order
            self.exchange_order_id = exchange.place_sell_limit_order(self.symbol, self.quantity, self.price)
        # If command succeeded, update status
        self.status = OrderState.PLACED
        self.time_placed = timezone.now()

        # Save to database
        self.save()

    def place_market(self, exchange: Exchange):
        """
        Places market order with exchange.
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
        self.time_placed = timezone.now()

        # Save to database
        self.save()

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

        # Fill price for market order
        if not self.price and self.status in (OrderState.CANCELLED_PARTIAL, OrderState.COMPLETED):
            self.price = new_status.price
