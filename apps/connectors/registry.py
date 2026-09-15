from __future__ import annotations

from typing import Type

from apps.connectors.base import ConnectorDriver

_REGISTRY: dict[str, Type[ConnectorDriver]] = {}


def register_connector(connector_type: str):
    def _wrap(cls: Type[ConnectorDriver]) -> Type[ConnectorDriver]:
        _REGISTRY[connector_type.lower()] = cls
        return cls

    return _wrap


def get_connector_driver(connector_type: str) -> ConnectorDriver:
    key = connector_type.lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "none"
        raise ValueError(f"No connector driver for '{connector_type}'. Available: {available}")
    return _REGISTRY[key]()


def registered_connector_types() -> list[str]:
    return sorted(_REGISTRY.keys())
