import logging
import random
from decimal import Decimal

from hummingbot.core.data_type.common import OrderType, PriceType
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class Wash(ScriptStrategyBase):
    order_base_amount_min = 2000
    order_base_amount_max = 5000
    delay_min = 45
    delay_max = 75
    trading_pair = "PINK-USDT"
    exchange = "polkadex"
    markets = {exchange: {trading_pair}}
    refresh_time = 0

    def on_tick(self):
        if self.refresh_time <= self.current_timestamp:
            self.cancel_all_orders()
            self.place_order()
            self.set_refresh_time()

    def set_refresh_time(self):
        self.refresh_time = self.current_timestamp + random.randint(self.delay_min, self.delay_max)

    def place_order(self):
        best_bid = self.connectors[self.exchange].get_price_by_type(self.trading_pair, PriceType.BestBid)
        best_ask = self.connectors[self.exchange].get_price_by_type(self.trading_pair, PriceType.BestAsk)
        if (best_ask - best_bid) / best_bid > .03:
            self.notify_hb_app_with_timestamp(f"Current Spread is:{round((best_ask - best_bid) / best_bid, 6)} which is too high, moving on")
            return

        amount_base = random.randint(self.order_base_amount_min * 100, self.order_base_amount_max * 100) / 100
        if bool(random.getrandbits(1)):
            self.sell(connector_name=self.exchange, trading_pair=self.trading_pair, amount=Decimal(amount_base), order_type=OrderType.LIMIT, price=Decimal(best_bid))
        else:
            self.buy(connector_name=self.exchange, trading_pair=self.trading_pair, amount=Decimal(amount_base), order_type=OrderType.LIMIT, price=Decimal(best_ask))

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.exchange):
            msg = (f"{self.exchange} { order.trading_pair} {order.client_order_id}")
            self.log_with_clock(logging.INFO, msg)
            # self.cancel(self.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        msg = (f"{event.trade_type.name} {round(event.amount, 2)} {event.trading_pair} {self.exchange} at {round(event.price, 6)}")
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)
