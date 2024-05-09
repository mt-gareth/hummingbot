from typing import Optional, Union

from pydantic import BaseModel

from hummingbot.smart_components.executors.arbitrage_executor.data_types import ArbitrageExecutorConfig
from hummingbot.smart_components.executors.dca_executor.data_types import DCAExecutorConfig
from hummingbot.smart_components.executors.position_executor.data_types import PositionExecutorConfig
from hummingbot.smart_components.executors.twap_executor.data_types import TWAPExecutorConfig
from hummingbot.smart_components.executors.xemm_executor.data_types import XEMMExecutorConfig
from hummingbot.smart_components.executors.mm_executor.data_types import MMExecutorConfig


class ExecutorAction(BaseModel):
    """
    Base class for bot actions.
    """
    controller_id: Optional[str] = "main"


class CreateExecutorAction(ExecutorAction):
    """
    Action to create an executor.
    """
    executor_config: Union[PositionExecutorConfig, DCAExecutorConfig, XEMMExecutorConfig, ArbitrageExecutorConfig, TWAPExecutorConfig, MMExecutorConfig]


class StopExecutorAction(ExecutorAction):
    """
    Action to stop an executor.
    """
    executor_id: str


class StoreExecutorAction(ExecutorAction):
    """
    Action to store an executor.
    """
    executor_id: str
