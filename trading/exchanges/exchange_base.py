from decimal import Decimal
from trading.enums import OrderState

# class ExchangeSymbol:
#     def __init__(self):
#         self.base_asset = None
#         self.quote_asset = None


class ExchangeOrderStatus:
    price: Decimal
    quantity: Decimal
    quantity_filled: Decimal
    status: OrderState


class Exchange:
    def get_last_price(self, symbol: str) -> Decimal:
        """
        Gets the price of the last transaction on a symbol.
        :param symbol: Symbol to get last price on.
        :return: Last transaction price.
        """
        raise NotImplementedError

    def get_bid_price(self, symbol: str) -> Decimal:
        """
        Gets the highest bid price on a symbol.
        :param symbol: Symbol to get bid price on.
        :return: Highest bid.
        """
        raise NotImplementedError

    def get_ask_price(self, symbol: str) -> Decimal:
        """
        Gets the lowest ask price on a symbol.
        :param symbol: Symbol to get ask price on.
        :return: Lowest ask.
        """
        raise NotImplementedError

    def get_order_status(self, symbol: str, order_id: str, last_state: OrderState) -> ExchangeOrderStatus:
        """
        Gets the current status of a placed order.
        :param symbol: Symbol that the order was placed on.
        :param order_id: ID for the order.
        :param last_state: The last ExchangeOrderStatus message received.
        :return: ExchangeOrderStatus representing the order's status.
        """
        raise NotImplementedError

    def place_buy_limit_order(self, symbol: str, quantity: Decimal, price: Decimal, test: bool = False) -> str:
        """
        Places a buy limit order.
        :param symbol: Symbol to buy.
        :param quantity: Quantity of symbol to buy.
        :param price: Price below which to buy the symbol.
        :param test: When True, if supported, order will be checked, but not placed.
        :return: ID unique to the order.
        """
        raise NotImplementedError

    def place_buy_market_order(self, symbol: str, quantity: Decimal, test: bool = False) -> str:
        """
        Places a buy order at market price.
        :param symbol: Symbol to buy.
        :param quantity: Quantity of symbol to buy.
        :param test: When True, if supported, order will be checked, but not placed.
        :return: ID unique to the order.
        """
        raise NotImplementedError
    
    def place_sell_limit_order(self, symbol: str, quantity: Decimal, price: Decimal, test: bool = False) -> str:
        """
        Places a sell limit order.
        :param symbol: Symbol to sell.
        :param quantity: Quantity of symbol to sell.
        :param price: Price below which to sell the symbol.
        :param test: When True, if supported, order will be checked, but not placed.
        :return: ID unique to the order.
        """
        raise NotImplementedError

    def place_sell_market_order(self, symbol: str, quantity: Decimal, test: bool = False) -> str:
        """
        Places a sell order at market price.
        :param symbol: Symbol to sell.
        :param quantity: Quantity of symbol to sell.
        :param test: When True, if supported, order will be checked, but not placed.
        :return: ID unique to the order.
        """
        raise NotImplementedError

    def cancel_order(self, symbol: str, order_id: str) -> None:
        """
        Cancels an order.
        :param symbol: Symbol that order is buying/selling.
        :param order_id: ID of order to be cancelled.
        """
        raise NotImplementedError

    def get_balance(self, asset: str) -> Decimal:
        """
        Gets the current balance of an asset.
        :param asset: Code of asset to check.
        :return: Balance of asset.
        """
        raise NotImplementedError
