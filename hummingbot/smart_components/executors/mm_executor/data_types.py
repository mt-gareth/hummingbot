from __future__ import annotations

from decimal import Decimal
from typing import Optional

from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.smart_components.executors.data_types import ExecutorConfigBase

class MMExecutorConfig(ExecutorConfigBase):
    type = "mm_executor"
    trading_pair: str
    connector_name: str
    side: TradeType
    spread: Decimal
    order_amount_quote: Decimal
    mid_price: Decimal
    refeash_time: int
    replace_time: int
    level_id: Optional[str] = None
