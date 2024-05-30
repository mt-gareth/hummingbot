import os
from typing import Dict, List, Set

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.clock import Clock
from hummingbot.smart_components.executors.wash_executor.data_types import WashExecutorConfig
from hummingbot.smart_components.models.executor_actions import CreateExecutorAction, StopExecutorAction
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase


class WashV2Config(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    markets: Dict[str, Set[str]] = 'polkadex.PINK-USDT'


class WashV2(StrategyV2Base):
    def __init__(self, connectors: Dict[str, ConnectorBase], config: WashV2Config):
        super().__init__(connectors, config)
        self.config = config  # Only for type checking

    def start(self, clock: Clock, timestamp: float) -> None:
        self._last_timestamp = timestamp

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        create_actions = []
        for connector_name in self.connectors:
            for trading_pair in self.market_data_provider.get_trading_pairs(connector_name):
                all_executors = self.get_all_executors()
                wash_executor = self.filter_executors(executors=all_executors, filter_func=lambda x: x.type == "wash_executor" and x.is_active)
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
