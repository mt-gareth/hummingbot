from decimal import Decimal

from hummingbot.smart_components.executors.data_types import ExecutorConfigBase


class WashExecutorConfig(ExecutorConfigBase):
    type: str = "wash_executor"
    trading_pair: str
    connector_name: str
    order_amount_min: Decimal
    order_amount_max: Decimal
    delay_min: int
    delay_max: int
