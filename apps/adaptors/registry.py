"""
CONCEPT TO LEARN: the Factory pattern (as a registry).

Instead of hardcoding `if source_type == "csv": CsvAdapter()` everywhere,
adaptors register themselves once, and calling code just asks the registry
for "the adapter for this source_type". This is exactly the pattern your
interview prep flagged as high-value (Factory pattern).
"""

from typing import Type
from .base import DataSourceAdapter

_ADAPTER_REGISTRY: dict[str, Type[DataSourceAdapter]] = {}


def register_adapter(source_type: str):
    """Decorator: @register_adapter('csv') on a DataSourceAdapter subclass."""
    def _wrap(cls: Type[DataSourceAdapter]) -> Type[DataSourceAdapter]:
        _ADAPTER_REGISTRY[source_type.lower()] = cls
        return cls
    return _wrap


def get_adapter(source_type: str) -> Type[DataSourceAdapter]:
    """Retrieve registered adapter class for given source_type, raising clear ValueError if missing."""
    key = source_type.lower()
    if key not in _ADAPTER_REGISTRY:
        available = ", ".join(sorted(_ADAPTER_REGISTRY.keys())) or "none"
        raise ValueError(
            f"No adapter registered for source type '{source_type}'. "
            f"Available registered adapters: [{available}]"
        )
    return _ADAPTER_REGISTRY[key]


def list_registered_adapters() -> list[str]:
    """Return a list of all currently registered adapter keys."""
    return sorted(set[str](_ADAPTER_REGISTRY.keys()))

