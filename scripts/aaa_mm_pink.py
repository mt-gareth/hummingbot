import os
import pprint
from decimal import Decimal
from typing import Dict, List, Set

import requests

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import TradeType
from hummingbot.smart_components.executors.mm_executor.data_types import MMExecutorConfig
from hummingbot.smart_components.executors.wash_executor.data_types import WashExecutorConfig
from hummingbot.smart_components.models.executor_actions import CreateExecutorAction, StopExecutorAction
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase


class MMMultiLevelConfig(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    markets: Dict[str, Set[str]] = 'polkadex.PINK-USDT'
    price_refresh_time: int = 5
    order_amount_quote: Decimal = 100
    levels: List = [
        {
            'id': 'step-1',
            'spread': Decimal("0.005"),
            'percent': Decimal("0.04"),
            'ttl': 300,
        }, {
            'id': 'step-2',
            'spread': Decimal("0.0075"),
            'percent': Decimal("0.06"),
            'ttl': 420,
        }, {
            'id': 'step-3',
            'spread': Decimal("0.01"),
            'percent': Decimal("0.08"),
            'ttl': 530,
        }, {
            'id': 'step-4',
            'spread': Decimal("0.015"),
            'percent': Decimal("0.10"),
            'ttl': 640,
        }, {
            'id': 'step-5',
            'spread': Decimal("0.020"),
            'percent': Decimal("0.12"),
            'ttl': 750,
        }, {
            'id': 'step-6',
            'spread': Decimal("0.025"),
            'percent': Decimal("0.10"),
            'ttl': 860,
        }, {
            'id': 'step-7',
            'spread': Decimal("0.03"),
            'percent': Decimal("0.11"),
            'ttl': 970,
        }, {
            'id': 'step-8',
            'spread': Decimal("0.035"),
            'percent': Decimal("0.12"),
            'ttl': 970,
        }, {
            'id': 'step-9',
            'spread': Decimal("0.04"),
            'percent': Decimal("0.13"),
            'ttl': 970,
        }, {
            'id': 'step-10',
            'spread': Decimal("0.045"),
            'percent': Decimal("0.14"),
            'ttl': 970,
        }]


class MMMultiLevel(StrategyV2Base):
    _last_price_check = None
    _mid_price = None

    def __init__(self, connectors: Dict[str, ConnectorBase], config: MMMultiLevelConfig):
        super().__init__(connectors, config)
        self.config = config  # Only for type checking

    def start(self, clock: Clock, timestamp: float) -> None:
        self._last_timestamp = timestamp

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        """
        Create actions proposal based on the current state of the executors.
        """
        create_actions = []
        for connector_name in self.connectors:
            for trading_pair in self.market_data_provider.get_trading_pairs(connector_name):
                if not self._last_price_check or not self._mid_price or self._last_price_check + self.config.price_refresh_time < self.current_timestamp:
                    # Get mid-price
                    mid_price = self.get_mid_price()
                    if mid_price:
                        self._mid_price = mid_price
                        self._last_price_check = self.current_timestamp
                if not self._mid_price:
                    return create_actions

                # Get active executors
                all_executors = self.get_all_executors()
                mm_executors = self.filter_executors(executors=all_executors, filter_func=lambda x: x.type == "mm_executor" and x.is_active)
                wash_executor = self.filter_executors(executors=all_executors, filter_func=lambda x: x.type == "wash_executor" and x.is_active)
                # pprint.pp(self.executor_orchestrator.executors)
                if self.executor_orchestrator.executors.get('main'):
                    for executor in self.executor_orchestrator.executors.get('main'):
                        if executor.config.type == "mm_executor":
                            executor.set_mid_price(self._mid_price)
                active_buy_position_executors = self.filter_executors(executors=mm_executors, filter_func=lambda x: x.side == TradeType.BUY and x.is_active)
                active_sell_position_executors = self.filter_executors(executors=mm_executors, filter_func=lambda x: x.side == TradeType.SELL and x.is_active)
                # If there is already enough executors running just bail
                if len(active_buy_position_executors) < len(self.config.levels) or len(active_sell_position_executors) < len(self.config.levels):
                    for level in self.config.levels:
                        # find current exicutor
                        this_buy_executor = self.filter_executors(executors=active_buy_position_executors, filter_func=lambda x: x.custom_info["level_id"] == level['id'])
                        if len(this_buy_executor) == 0:
                            create_actions.append(CreateExecutorAction(
                                executor_config=MMExecutorConfig(
                                    timestamp=self.current_timestamp,
                                    trading_pair=trading_pair,
                                    connector_name=connector_name,
                                    side=TradeType.BUY,
                                    spread=level['spread'],
                                    order_amount_quote=self.config.order_amount_quote * level['percent'],
                                    mid_price=self._mid_price,
                                    refeash_time=level['ttl'],
                                    replace_time=30,
                                    level_id=level['id']
                                )
                            ))

                        this_sell_executor = self.filter_executors(executors=active_sell_position_executors, filter_func=lambda x: x.custom_info["level_id"] == level['id'])
                        if len(this_sell_executor) == 0:
                            create_actions.append(CreateExecutorAction(
                                executor_config=MMExecutorConfig(
                                    timestamp=self.current_timestamp,
                                    trading_pair=trading_pair,
                                    connector_name=connector_name,
                                    side=TradeType.SELL,
                                    spread=level['spread'],
                                    order_amount_quote=self.config.order_amount_quote * level['percent'],
                                    mid_price=self._mid_price,
                                    refeash_time=level['ttl'] + 25,
                                    replace_time=30,
                                    level_id=level['id']
                                )
                            ))
                if len(wash_executor) < 1:
                    create_actions.append(CreateExecutorAction(
                        executor_config=WashExecutorConfig(
                            timestamp=self.current_timestamp,
                            trading_pair=trading_pair,
                            connector_name=connector_name,
                            order_amount_min=2000,
                            order_amount_max=5000,
                            delay_min=45,
                            delay_max=75
                        )
                    ))
        return create_actions

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        stop_actions = []
        return stop_actions

    def get_mid_price(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
        response = requests.get('https://router-api.stellaswap.com/api/v2/quote/0xfFfFFfFf30478fAFBE935e466da114E14fB3563d/0xFFFFFFfFea09FB06d082fd1275CD48b191cbCD1d/100000000000/0xaF24ECb3912D154Ce9f35eeFb21452F0dCa31C5D/50', headers=headers)
        json_data = response.json() if response and response.status_code == 200 else None
        mid_price = None
        if json_data and 'result' in json_data:
            if 'amountOut' in json_data['result']:
                mid_price = Decimal(json_data['result']['amountOut']) / 10000000
        if mid_price is None:
            pprint.pp(response)
        return mid_price
