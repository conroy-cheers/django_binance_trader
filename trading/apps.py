from django.apps import AppConfig
from trading import tasks


class TradingAppConfig(AppConfig):
    name = 'trading'
    verbose_name = "Django Trading"

    def ready(self):
        # Startup code here
        tasks.trade_symbol.delay(args=('NEBLBNB', ))
