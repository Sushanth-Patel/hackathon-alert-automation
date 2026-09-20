"""Base notifier interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Union, List


class BaseNotifier(ABC):
    """Abstract base class for notification channels."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def send(self, content: Union[str, List[str]]) -> bool:
        """Send notification digest or list of message chunks."""
        pass
