import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Union

from hummingbot.core.data_type.common import OrderType, PositionAction, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    BuyOrderCreatedEvent,
    MarketOrderFailureEvent,
    OrderFilledEvent,
    SellOrderCompletedEvent,
    SellOrderCreatedEvent,
)
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.strategy_v2.executors.executor_base import ExecutorBase
from hummingbot.strategy_v2.executors.mm_executor.data_types import MMExecutorConfig
from hummingbot.strategy_v2.models.base import RunnableStatus
from hummingbot.strategy_v2.models.executors import CloseType, TrackedOrder


class MMExecutor(ExecutorBase):
    _logger = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, strategy: ScriptStrategyBase, config: MMExecutorConfig,
                 update_interval: float = 1.0, max_retries: int = 10):
        super().__init__(strategy=strategy, config=config, connectors=[config.connector_name], update_interval=update_interval)
        self.config: MMExecutorConfig = config

        # Order tracking
        self._open_order: Optional[TrackedOrder] = None
        self._failed_orders: List[TrackedOrder] = []

        self._mid_price = self.config.mid_price

        self._current_retries = 0
        self._max_retries = max_retries

        self._refresh_time = self.connector_timestamp()
        self.set_refresh_time(self.config.refeash_time)

        """
        type = "mm_executor"
        trading_pair: str
        connector_name: str
        side: TradeType
        spread: Decimal
        order_amount_quote: Decimal
        mid_price: Decimal
        refeash_time: int
        level_id: Optional[str] = None
        """
        """
        We will be taking in a mid_price, spread, and amount and maintining an order a the price
        if the order is filled we will replace the order after X amount of time
        if the order is partially filled we wil replace the order after X amount of time
        if the refresh time has been reached we will refresh the the order
        if the mid_price has changed to put our order at a diffrent price then 2x our desired spread we will refresh the order immediatly
        """

    @property
    def entry_price(self) -> Decimal:
        return self._mid_price * (1 - self.config.spread) if self.config.side == TradeType.BUY else self._mid_price * (1 + self.config.spread)

    @property
    def entry_amount(self) -> Decimal:
        return self.config.order_amount_quote / self.entry_price

    async def control_task(self):
        if self.status == RunnableStatus.RUNNING:
            if not self._open_order:
                self.place_open_order()
            elif self.connector_timestamp() > self._refresh_time:
                self.renew_order()
        elif self.status == RunnableStatus.SHUTTING_DOWN:
            await self.control_shutdown_process()
        self.evaluate_max_retries()

    async def control_shutdown_process(self):
        if not self._open_order or self._open_order.is_done:
            self.stop()
        else:
            self.cancel_open_order()
            self._current_retries += 1
        await asyncio.sleep(1.0)

    def connector_timestamp(self):
        return self.connectors[self.config.connector_name].current_timestamp

    def set_refresh_time(self, seconds_from_now: int):
        self._refresh_time = self.connector_timestamp() + seconds_from_now

    def set_mid_price(self, mid_price):
        self._mid_price = mid_price

    def early_stop(self):
        self.cancel_open_order()
        self.close_type = CloseType.EARLY_STOP
        self._status = RunnableStatus.SHUTTING_DOWN

    def evaluate_max_retries(self):
        if self._current_retries > self._max_retries:
            self.close_type = CloseType.FAILED
            self.stop()

    def place_open_order(self):
        order_id = self.place_order(
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            order_type=OrderType.LIMIT,
            amount=self.entry_amount,
            price=self.entry_price,
            side=self.config.side,
            position_action=PositionAction.OPEN,
        )
        self._open_order = TrackedOrder(order_id=order_id)
        self.logger().debug("Placing open order")

    def renew_order(self):
        self.cancel_open_order()
        self.place_open_order()
        self.set_refresh_time(self.config.refeash_time)
        self.logger().debug("Renewing order")

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
            self.set_refresh_time(self.config.replace_time)

    def process_order_filled_event(self, _, market, event: OrderFilledEvent):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order.order = self.get_in_flight_order(self.config.connector_name, event.order_id)

    def process_order_canceled_event(self, _, market, event: OrderFilledEvent):
        if self._open_order and self._open_order.order_id == event.order_id:
            self._open_order = None

    def process_order_failed_event(self, _, market, event: MarketOrderFailureEvent):
        self._current_retries += 1
        self._failed_orders.append(self._open_order)
        self._open_order = None
        self.logger().error(f"Open order failed. Retrying {self._current_retries}/{self._max_retries}")

    def get_custom_info(self) -> Dict:
        return {
            "level_id": self.config.level_id,
            "current_position_average_price": self.entry_price,
            "side": self.config.side,
            "current_retries": self._current_retries,
            "max_retries": self._max_retries
        }

    def to_format_status(self, scale=1.0):
        lines = []
        lines.extend([f"""
| Trading Pair: {self.config.trading_pair} | Exchange: {self.config.connector_name} | Side: {self.config.side} |
| Entry price: {self.entry_price:.6f} | Amount: {self.entry_amount:.4f}
| Close Type: {self.close_type}
    """])
        return lines

    def validate_sufficient_balance(self):
        order_candidate = OrderCandidate(
            trading_pair=self.config.trading_pair,
            is_maker=True,
            order_type=OrderType.LIMIT,
            order_side=self.config.side,
            amount=self.entry_amount,
            price=self.entry_price,
        )
        adjusted_order_candidates = self.adjust_order_candidates(self.config.connector_name, [order_candidate])
        if adjusted_order_candidates[0].amount == Decimal("0"):
            self.close_type = CloseType.INSUFFICIENT_BALANCE
            self.logger().error("Not enough budget to open position.")
            self.stop()

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
