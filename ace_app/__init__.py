"""Core package for the Ace desktop application."""

from .config import AppConfig, ConfigError
from .models import AppSnapshot, Operation, OperationState, Target, Turn

__all__ = [
    "AppConfig",
    "AppSnapshot",
    "ConfigError",
    "Operation",
    "OperationState",
    "Target",
    "Turn",
]

__version__ = "0.1.0"
