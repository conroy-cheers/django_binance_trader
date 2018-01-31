from enum import Enum


class OrderState(Enum):
    """
    Represents the state of a buy/sell order.
    """
    PENDING = 1  # Has not yet been sent to exchange.
    PLACED = 2  # Has been placed with exchange, but is not yet filling.
    FILLING = 3  # Has been placed with exchange and is partially filled.
    COMPLETED = 4  # Has been placed with exchange and completely filled.
    CANCELLED = 5  # Was placed with exchange and cancelled before partially or completely filling.
    CANCELLED_PARTIAL = 6  # Was placed with exchange and partially filled before being cancelled.


ORDER_STATE_TERMINAL_VALUES = (
    OrderState.COMPLETED.value,
    OrderState.CANCELLED.value,
    OrderState.CANCELLED_PARTIAL.value
)


class OrderSide(Enum):
    """
    Represents the direction of a buy/sell order.
    """
    BUY = 1
    SELL = 2
