from binance.client import Client
from binance import enums, exceptions
from decimal import Decimal
from django.conf import settings
from .exchange_base import Exchange, ExchangeOrderStatus
from trading.enums import OrderState
from .exceptions import APIError, OrderValueTooLow, UnknownSymbol, OrderPriceInvalid, LotSizeInvalid, \
    ExcessiveRoundingError

from pprint import pprint


class BinanceSymbol:
    symbol_name: str

    base_asset: str
    base_asset_precision: int

    quote_asset: str
    quote_asset_precision: int

    max_price: Decimal
    min_price: Decimal
    price_step: Decimal

    max_quantity: Decimal
    min_quantity: Decimal
    quantity_step: Decimal

    min_value: Decimal

    trading_available: bool

    @classmethod
    def from_dict(cls, symbol_dict: dict) -> 'BinanceSymbol':
        """
        Creates an instance from a symbol dictionary provided by the Binance API.
        :param symbol_dict: Symbol dict from Binance API.
        :return: Populated BinanceSymbol instance.
        """
        instance = cls()
        instance.symbol_name = symbol_dict['symbol']
        instance.base_asset = symbol_dict['baseAsset']
        instance.base_asset_precision = int(symbol_dict['baseAssetPrecision'])
        instance.quote_asset = symbol_dict['quoteAsset']
        instance.quote_asset_precision = int(symbol_dict['quotePrecision'])

        filters = symbol_dict['filters']
        price_filter_dict = next(f for f in filters if f['filterType'] == 'PRICE_FILTER')
        lot_size_dict = next(f for f in filters if f['filterType'] == 'LOT_SIZE')
        min_notional_dict = next(f for f in filters if f['filterType'] == 'MIN_NOTIONAL')

        instance.max_price = Decimal(price_filter_dict['maxPrice'].rstrip('0').rstrip('.'))
        instance.min_price = Decimal(price_filter_dict['minPrice'].rstrip('0').rstrip('.'))
        instance.price_step = Decimal(price_filter_dict['tickSize'].rstrip('0').rstrip('.'))
        instance.max_quantity = Decimal(lot_size_dict['maxQty'].rstrip('0').rstrip('.'))
        instance.min_quantity = Decimal(lot_size_dict['minQty'].rstrip('0').rstrip('.'))
        instance.quantity_step = Decimal(lot_size_dict['stepSize'].rstrip('0').rstrip('.'))
        instance.min_value = Decimal(min_notional_dict['minNotional'].rstrip('0').rstrip('.'))
        instance.trading_available = (symbol_dict['status'] == 'TRADING')

        return instance

    def __repr__(self):
        return f"<BinanceSymbol: {self.symbol_name:s} {self.base_asset:s}/{self.quote_asset:s}>"


class BinanceExchange(Exchange):
    def __init__(self, api_key: str, api_secret: str):
        self.client = Client(api_key, api_secret)
        self.symbols: dict = {}  # Dictionary mapping symbol names to BinanceSymbol instances
        self.update_symbols()

    def update_symbols(self):
        info = self.client.get_exchange_info()

        for symbol_dict in info['symbols']:
            # Create BinanceSymbol and store it in self.symbols, with the symbol name as the key
            symbol = BinanceSymbol.from_dict(symbol_dict)
            self.symbols[symbol.symbol_name] = symbol

        pprint(self.symbols)

    @staticmethod
    def process_api_error(exception: exceptions.BinanceAPIException) -> APIError:
        """
        Returns a more specific API exception class for the given BinanceAPIException, if available.
        :param exception: A BinanceAPIException instance.
        :return: Instance of an appropriate subclass of APIError, if available, else an instance of APIError.
        """
        if 'MIN_NOTIONAL' in exception.message:
            return OrderValueTooLow(message=exception.message)
        else:
            return APIError(message=exception.message)

    def get_symbol_info(self, symbol: str) -> BinanceSymbol:
        """
        Checks that the provided symbol is listed on the exchange.
        :param symbol: Symbol to check.
        :return: BinanceSymbol for the requested symbol name.
        :raises UnknownSymbol: When symbol is not listed.
        """
        symbol_info = self.symbols.get(symbol, None)
        if not symbol_info:
            raise UnknownSymbol(f"Unknown symbol \"{symbol:s}\"")
        return symbol_info

    def check_price(self, symbol: str, price: Decimal) -> Decimal:
        """
        Checks that the provided price is valid for the provided symbol.
        :param symbol: Symbol to check.
        :param price: Price to check.
        :return: Price, rounded to the correct step size.
        :raises OrderPriceInvalid: When price is not valid.
        """
        symbol_info = self.get_symbol_info(symbol)

        # Check min/max bounds
        if price < symbol_info.min_price:
            raise OrderPriceInvalid(
                f"Price {price} for symbol {symbol} is less than allowed minimum of {symbol_info.min_price}")
        elif price > symbol_info.max_price:
            raise OrderPriceInvalid(
                f"Price {price} for symbol {symbol} is greater than allowed maximum of {symbol_info.max_price}")

        # Constrain to step size and check rounding
        rounded = price.quantize(symbol_info.price_step)
        rounding_error = abs(rounded - price) / price
        if rounding_error >= settings.TRADING_MAXIMUM_ROUNDING_ERROR:
            raise ExcessiveRoundingError(
                f"Rounding {price} to price step {symbol_info.price_step} for symbol {symbol} would cause"
                "rounding error of {rounding_error:.1%}, which is larger than the allowed rounding error of "
                "{settings.TRADING_MAXIMUM_ROUNDING_ERROR:.1%}")
        else:
            return rounded

    def check_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        """
        Checks that the provided quantity is valid for the provided symbol.
        :param symbol: Symbol to check.
        :param quantity: Quantity to check.
        :return: Quantity, rounded to the correct step size.
        :raises LotSizeInvalid: When quantity is not valid.
        """
        symbol_info = self.get_symbol_info(symbol)

        # Check min/max bounds
        if quantity < symbol_info.min_quantity:
            raise LotSizeInvalid(
                f"Quantity {quantity} of symbol {symbol} is less than allowed minimum of {symbol_info.min_quantity}")
        elif quantity > symbol_info.max_quantity:
            raise LotSizeInvalid(
                f"Quantity {quantity} of symbol {symbol} is greater than allowed maximum of {symbol_info.max_quantity}")

        # Constrain to step size and check rounding
        rounded = quantity.quantize(symbol_info.quantity_step)
        rounding_error = abs(rounded - quantity) / quantity
        if rounding_error >= settings.TRADING_MAXIMUM_ROUNDING_ERROR:
            raise ExcessiveRoundingError(
                f"Rounding {quantity} to quantity step {symbol_info.quantity_step} for symbol {symbol} would cause"
                "rounding error of {rounding_error:.1%}, which is larger than the allowed rounding error of "
                "{settings.TRADING_MAXIMUM_ROUNDING_ERROR:.1%}")
        else:
            return rounded

    def get_last_price(self, symbol: str) -> Decimal:
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            return Decimal(ticker['lastPrice'])
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def get_bid_price(self, symbol: str) -> Decimal:
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            return Decimal(ticker['bidPrice'])
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def get_ask_price(self, symbol: str) -> Decimal:
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            return Decimal(ticker['askPrice'])
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def get_order_status(self, symbol: str, order_id: str, last_state: OrderState) -> ExchangeOrderStatus:
        try:
            response = self.client.get_order(symbol=symbol, orderId=order_id)

            status = ExchangeOrderStatus()
            status.price = Decimal(response['price'])
            status.quantity = Decimal(response['origQty'])
            status.quantity_filled = Decimal(response['executedQty'])

            response_status = response['status']
            if response_status == 'NEW':
                status.status = OrderState.PLACED
            elif response_status == 'PARTIALLY_FILLED':
                status.status = OrderState.FILLING
            elif response_status == 'FILLED':
                status.status = OrderState.COMPLETED
            elif response_status == 'CANCELED' or response_status == 'EXPIRED':
                if last_state == OrderState.FILLING:
                    status.status = OrderState.CANCELLED_PARTIAL
                else:
                    status.status = OrderState.CANCELLED
            elif response_status == 'PENDING_CANCEL':
                status.status = last_state
            elif response_status == 'REJECTED':
                status.status = OrderState.CANCELLED
            else:
                raise APIError(f"Unknown response status {response_status:s}")

            return status
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def place_buy_limit_order(self, symbol: str, quantity: Decimal, price: Decimal, test: bool = False) -> str:
        # Check and round parameters
        price = self.check_price(symbol, price)
        quantity = self.check_quantity(symbol, quantity)

        try:
            if test:
                self.client.create_test_order(symbol=symbol, quantity=quantity, price=str(price),
                                              side=enums.SIDE_BUY, type=enums.ORDER_TYPE_LIMIT,
                                              timeInForce=enums.TIME_IN_FORCE_GTC)
                return ""
            else:
                return self.client.order_limit_buy(symbol=symbol, quantity=quantity, price=str(price))['orderId']
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def place_buy_market_order(self, symbol: str, quantity: Decimal, test: bool = False) -> str:
        # Check and round parameters
        quantity = self.check_quantity(symbol, quantity)

        try:
            if test:
                self.client.create_test_order(symbol=symbol, quantity=quantity,
                                              side=enums.SIDE_BUY, type=enums.ORDER_TYPE_MARKET,
                                              timeInForce=enums.TIME_IN_FORCE_GTC)
                return ""
            else:
                return self.client.order_market_buy(symbol=symbol, quantity=quantity)['orderId']
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def place_sell_limit_order(self, symbol: str, quantity: Decimal, price: Decimal, test: bool = False) -> str:
        # Check and round parameters
        price = self.check_price(symbol, price)
        quantity = self.check_quantity(symbol, quantity)

        try:
            if test:
                self.client.create_test_order(symbol=symbol, quantity=quantity, price=str(price),
                                              side=enums.SIDE_SELL, type=enums.ORDER_TYPE_LIMIT,
                                              timeInForce=enums.TIME_IN_FORCE_GTC)
                return ""
            else:
                return self.client.order_limit_sell(symbol=symbol, quantity=quantity, price=str(price))['orderId']
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def place_sell_market_order(self, symbol: str, quantity: Decimal, test: bool = False) -> str:
        # Check and round parameters
        quantity = self.check_quantity(symbol, quantity)

        try:
            if test:
                self.client.create_test_order(symbol=symbol, quantity=quantity,
                                              side=enums.SIDE_SELL, type=enums.ORDER_TYPE_MARKET,
                                              timeInForce=enums.TIME_IN_FORCE_GTC)
                return ""
            else:
                return self.client.order_market_sell(symbol=symbol, quantity=quantity)['orderId']
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def cancel_order(self, symbol: str, order_id: str) -> None:
        try:
            self.client.cancel_order(symbol=symbol, orderId=order_id)
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e

    def get_balance(self, asset: str) -> Decimal:
        try:
            response = self.client.get_asset_balance(asset)
            return Decimal(response['free'])
        except exceptions.BinanceAPIException as e:
            raise self.process_api_error(e) from e
