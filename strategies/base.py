from abc import ABC, abstractmethod
import logging


class BaseStrategy(ABC):
    def __init__(self, strategy_id: str, params: dict):
        self.id = strategy_id
        self.params = params
        self.log = logging.getLogger(f"strategy.{strategy_id}")

    @abstractmethod
    def setup(self, reset: bool = False) -> None: ...

    @abstractmethod
    def tick(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...
