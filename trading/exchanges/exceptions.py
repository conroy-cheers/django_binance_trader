class ExchangeException(Exception):
    """
    Base class for Exchange exceptions.
    """
    def __init__(self, *args, **kwargs):
        super(ExchangeException, self).__init__(*args)
        self.message = kwargs.pop('message', "No exception message supplied")

    def __str__(self):
        return f"{self.__class__.__name__:s}: {self.message:s}"


class InsufficientFunds(ExchangeException):
    pass


class OrderNotFound(ExchangeException):
    pass


class ExcessiveRoundingError(ExchangeException):
    """
    Raised when the change to a price or quantity caused by rounding would exceed the maximum allowed rounding error
    defined in settings
    """
    pass


class APIError(ExchangeException):
    """
    Raised when the exchange rejected the request for some reason. Assume that no action has been taken here.
    """
    pass


class OrderValueTooLow(APIError):
    """
    Raised when the value of the order (for Binance, in BTC) is too small.
    """
    pass


class OrderPriceInvalid(APIError):
    """
    Raised when an order's price is too low, too high, or does not constrain to the step size.
    """
    pass


class LotSizeInvalid(APIError):
    """
    Raised when an order's size is too small, too large, or does not constrain to the step size.
    """
    pass


class UnknownSymbol(APIError):
    """
    Raised when an order is placed with a symbol not available on the exchange.
    """
    pass
