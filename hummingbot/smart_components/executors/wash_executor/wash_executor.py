import logging
import random
from decimal import Decimal
from typing import Dict, Union

from hummingbot.core.data_type.common import OrderType, PositionAction, PriceType, TradeType
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    BuyOrderCreatedEvent,
    MarketOrderFailureEvent,
    OrderFilledEvent,
    SellOrderCompletedEvent,
    SellOrderCreatedEvent,
)
from hummingbot.logger import HummingbotLogger
from hummingbot.smart_components.executors.executor_base import ExecutorBase
from hummingbot.smart_components.executors.wash_executor.data_types import WashExecutorConfig
from hummingbot.smart_components.models.base import SmartComponentStatus
from hummingbot.smart_components.models.executors import TrackedOrder
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class WashExecutor(ExecutorBase):
    _logger = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, strategy: ScriptStrategyBase, config: WashExecutorConfig,
                 update_interval: float = 1.0, max_retries: int = 10):
        super().__init__(strategy=strategy, config=config, connectors=[config.connector_name], update_interval=update_interval)
        self.config: WashExecutorConfig = config
        self._open_order = None
        self._refresh_time = self.connector_timestamp()

    async def control_task(self):
        if self.status == SmartComponentStatus.RUNNING:
            if self.connector_timestamp() > self._refresh_time:
                self.cancel_open_order()
                self.place_orders()
                self.set_refresh_time()
        elif self.status == SmartComponentStatus.SHUTTING_DOWN:
            self.stop()

    def connector_timestamp(self):
        return self.connectors[self.config.connector_name].current_timestamp

    def set_refresh_time(self):
        self._refresh_time = self.connector_timestamp() + random.randint(self.config.delay_min, self.config.delay_max)

    def place_orders(self):
        best_bid = self.get_price(self.config.connector_name, self.config.trading_pair, PriceType.BestBid)
        best_ask = self.get_price(self.config.connector_name, self.config.trading_pair, PriceType.BestAsk)
        if (best_ask - best_bid) / best_bid > .02:
            self.logger().info(f"Current Spread is:{round((best_ask - best_bid) / best_bid, 6)} which is too high, moving on")
            return

        amount = round(Decimal(random.randint(self.config.order_amount_min * 100, self.config.order_amount_max * 100) / 100), 0)
        is_buy = bool(random.getrandbits(1))
        order_id = self.place_order(
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=Decimal(best_ask) if is_buy else Decimal(best_bid),
            side=TradeType.BUY if is_buy else TradeType.SELL,
            position_action=PositionAction.NIL,
        )
        self._open_order = TrackedOrder(order_id=order_id)

    def cancel_open_order(self):
        if self._open_order and self._open_order.order_id:
            self._strategy.cancel(
                connector_name=self.config.connector_name,
                trading_pair=self.config.trading_pair,
                order_id=self._open_order.order_id
            )

    def process_order_created_event(self, _, market, event: Union[BuyOrderCreatedEvent, SellOrderCreatedEvent]):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = self.get_in_flight_order(self.config.connector_name, event.order_id)

    def process_order_completed_event(self, _, market, event: Union[BuyOrderCompletedEvent, SellOrderCompletedEvent]):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = self.get_in_flight_order(self.config.connector_name, event.order_id)

    def process_order_filled_event(self, _, market, event: OrderFilledEvent):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = self.get_in_flight_order(self.config.connector_name, event.order_id)

    def process_order_canceled_event(self, _, market, event: OrderFilledEvent):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = None

    def process_order_failed_event(self, _, market, event: MarketOrderFailureEvent):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = self.get_in_flight_order(self.config.connector_name, event.order_id)

    def get_custom_info(self) -> Dict:
        return {
            "type": "wash",
        }

    def early_stop(self):
        self.cancel_open_order()
        self.status == SmartComponentStatus.SHUTTING_DOWN

    def to_format_status(self, scale=1.0):
        lines = []
        lines.extend([f"""Trading Pair: {self.config.trading_pair} | Exchange: {self.config.connector_name}"""])
        return lines

    def validate_sufficient_balance(self):
        pass

    def get_net_pnl_quote(self) -> Decimal:
        """
        Returns the net profit or loss in quote currency.
        """
        return Decimal("0")

    def get_net_pnl_pct(self) -> Decimal:
        """
        Returns the net profit or loss in percentage.
        """
        return Decimal("0")

    def get_cum_fees_quote(self) -> Decimal:
        """
        Returns the cumulative fees in quote currency.
        """
        return Decimal("0")
