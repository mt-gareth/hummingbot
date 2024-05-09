import os
import requests
import pprint
from decimal import Decimal
from typing import Dict, List, Set

from pydantic import Field, validator

from hummingbot.client.config.config_data_types import ClientFieldData
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PositionMode, PriceType, TradeType
from hummingbot.data_feed.candles_feed.candles_factory import CandlesConfig
from hummingbot.smart_components.executors.position_executor.data_types import (
    PositionExecutorConfig,
    TripleBarrierConfig,
)
from hummingbot.smart_components.models.executor_actions import CreateExecutorAction, StopExecutorAction
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase


class PMMWithPositionExecutorConfig(StrategyV2ConfigBase):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))
    candles_config: List[CandlesConfig] = []
    markets: Dict[str, Set[str]] = {}
    controllers_config: List[str] = []
    order_amount_quote: Decimal = 100
    executor_refresh_time: int = 60 * 1
    leverage: int = 1
    position_mode: PositionMode = PositionMode["HEDGE"]
    # Triple Barrier Configuration
    stop_loss: Decimal = Decimal("0.03")
    take_profit: Decimal = Decimal("0.01")
    time_limit: int = 60 * 45
    take_profit_order_type: OrderType = OrderType["LIMIT"]
    levels: List = [{
            'id': 'step-1',
            'spread': Decimal("0.005"),
            'percent': Decimal("0.10"),
            'ttl': 300,
        },{
            'id': 'step-2',
            'spread': Decimal("0.0075"),
            'percent': Decimal("0.15"),
            'ttl': 420,
        },{
            'id': 'step-3',
            'spread': Decimal("0.01"),
            'percent': Decimal("0.20"),
            'ttl': 530,
        },{
            'id': 'step-4',
            'spread': Decimal("0.015"),
            'percent': Decimal("0.25"),
            'ttl': 640,
        },{
            'id': 'step-5',
            'spread': Decimal("0.019"),
            'percent': Decimal("0.30"),
            'ttl': 750,
        }]

    @property
    def triple_barrier_config(self) -> TripleBarrierConfig:
        return TripleBarrierConfig(
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            time_limit=10,
            open_order_type=OrderType.LIMIT,
            take_profit_order_type=OrderType.LIMIT,
            stop_loss_order_type=OrderType.MARKET,  # Defaulting to MARKET as per requirement
            time_limit_order_type=OrderType.MARKET,  # Defaulting to MARKET as per requirement
        )


class PMMSingleLevel(StrategyV2Base):
    account_config_set = False

    def __init__(self, connectors: Dict[str, ConnectorBase], config: PMMWithPositionExecutorConfig):
        super().__init__(connectors, config)
        self.config = config  # Only for type checking

    def start(self, clock: Clock, timestamp: float) -> None:
        self._last_timestamp = timestamp

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        """
        Create actions proposal based on the current state of the executors.
        """
        create_actions = []
        connector_name = 'polkadex'
        trading_pair = 'PINK-USDT'

        #Get active executors
        all_executors = self.get_all_executors()
                
        active_buy_position_executors = self.filter_executors(executors=all_executors, filter_func=lambda x: x.side == TradeType.BUY and x.is_active)
        active_sell_position_executors = self.filter_executors(executors=all_executors, filter_func=lambda x: x.side == TradeType.SELL and x.is_active)

        #Filter out old orders
        for order in self.get_active_orders(connector_name=connector_name):
            if self.current_timestamp - order.creation_timestamp >= self.config.levels[-1]['ttl'] * 1.5:
                self.cancel(connector_name, trading_pair, order.client_order_id)

        #If there is already enough executors running just bail
        if len(active_buy_position_executors) >= len(self.config.levels) and len(active_sell_position_executors) >= len(self.config.levels):
            return create_actions

        # Get mid-price
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
        response = requests.get('https://router-api.stellaswap.com/api/v2/quote/0xfFfFFfFf30478fAFBE935e466da114E14fB3563d/0xFFFFFFfFea09FB06d082fd1275CD48b191cbCD1d/100000000000/0xaF24ECb3912D154Ce9f35eeFb21452F0dCa31C5D/50', headers=headers)
        json_data = response.json() if response and response.status_code == 200 else None
        mid_price = None
        if json_data and 'result' in json_data:
            if 'amountOut' in json_data['result']:
                mid_price = Decimal(json_data['result']['amountOut']) / 10000000

        #If we did not get the midprice just bail
        if mid_price == None:
            pprint.pp(response)
            return create_actions
        
        for level in self.config.levels:
            #find current exicutor
            this_buy_executor = self.filter_executors(executors=all_executors, filter_func=lambda x: x.side == TradeType.BUY and x.is_active and x.custom_info["level_id"] == level['id'])
            if(len(this_buy_executor) == 0) :
                order_price = mid_price * (1 - level['spread'])
                order_amount = (self.config.order_amount_quote * level['percent']) / order_price
                create_actions.append(CreateExecutorAction(
                    executor_config=PositionExecutorConfig(
                        timestamp=self.current_timestamp,
                        trading_pair=trading_pair,
                        connector_name=connector_name,
                        side=TradeType.BUY,
                        amount=order_amount,
                        entry_price=order_price,
                        triple_barrier_config=self.config.triple_barrier_config,
                        leverage=1,
                        level_id=level['id']
                    )
                ))

            this_sell_executor = self.filter_executors(executors=all_executors, filter_func=lambda x: x.side == TradeType.SELL and x.is_active and x.custom_info["level_id"] == level['id'])
            if(len(this_sell_executor) == 0) :
                order_price = mid_price * (1 + level['spread'])
                order_amount = (self.config.order_amount_quote * level['percent']) / order_price
                create_actions.append(CreateExecutorAction(
                    executor_config=PositionExecutorConfig(
                        timestamp=self.current_timestamp,
                        trading_pair=trading_pair,
                        connector_name=connector_name,
                        side=TradeType.SELL,
                        amount=order_amount,
                        entry_price=order_price,
                        triple_barrier_config=self.config.triple_barrier_config,
                        leverage=1,
                        level_id=level['id']
                    )
                ))
        
        return create_actions

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        stop_actions = []
        stop_actions.extend(self.executors_to_refresh())
        stop_actions.extend(self.executors_to_early_stop())
        return stop_actions

    def executors_to_refresh(self) -> List[StopExecutorAction]:
        stop_actions = []
        all_executors = self.get_all_executors()
        for ex in all_executors:
            if(ex.is_trading):
                stop_actions.append(StopExecutorAction(executor_id=ex.id))

        for level in self.config.levels:
            executors_to_refresh = self.filter_executors(
                executors=all_executors,
                filter_func=lambda x: x.is_active and x.custom_info["level_id"] == level['id'] and self.current_timestamp - x.timestamp > level['ttl'])
            if len(executors_to_refresh) > 0:
                stop_actions.append(StopExecutorAction(executor_id=executors_to_refresh[0].id))

        return stop_actions

    def executors_to_early_stop(self) -> List[StopExecutorAction]:
        return []
