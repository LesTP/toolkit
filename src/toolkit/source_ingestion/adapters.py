"""Internal adapter protocol and registry for Source Ingestion."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from inspect import Parameter, signature
from typing import Protocol

from toolkit.source_ingestion.types import AdapterConfig, ContentItem, IngestionConfig

LastSeenMarker = str | int | float | datetime | None


@dataclass
class AdapterItemError:
    """Adapter-local item failure, converted to public IngestionError by the manager."""

    error: str
    url: str | None = None


@dataclass
class AdapterPollResult:
    """Internal adapter poll result with an optional next last-seen marker."""

    items: list[ContentItem] = field(default_factory=list)
    errors: list[AdapterItemError] = field(default_factory=list)
    next_marker: LastSeenMarker = None


class SourceAdapter(Protocol):
    """Internal interface implemented by concrete source adapters."""

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        """Fetch content newer than last_seen_marker."""


AdapterFactory = Callable[..., SourceAdapter]


class AdapterRegistry:
    """Immutable internal adapter factory registry."""

    def __init__(self, factories: Mapping[str, AdapterFactory]) -> None:
        self._factories = dict(factories)
        for adapter_type, factory in self._factories.items():
            if not adapter_type:
                raise ValueError("adapter_type is required")
            if not callable(factory):
                raise TypeError(f"adapter factory for {adapter_type} must be callable")

    @classmethod
    def pending(cls, adapter_types: set[str]) -> "AdapterRegistry":
        return cls(
            {
                adapter_type: pending_adapter_factory(adapter_type)
                for adapter_type in adapter_types
            }
        )

    def with_factories(
        self, factories: Mapping[str, AdapterFactory] | None
    ) -> "AdapterRegistry":
        if not factories:
            return self
        merged = dict(self._factories)
        merged.update(factories)
        return AdapterRegistry(merged)

    def supports(self, adapter_type: str) -> bool:
        return adapter_type in self._factories

    def create(
        self, config: AdapterConfig, ingestion_config: IngestionConfig | None = None
    ) -> SourceAdapter:
        factory = self._factories[config.adapter_type]
        if ingestion_config is None or not _accepts_ingestion_config(factory):
            return factory(config)
        return factory(config, ingestion_config)


class PendingAdapter:
    """Placeholder for ARCH adapter types whose fetching is implemented later."""

    def __init__(self, adapter_type: str) -> None:
        self.adapter_type = adapter_type

    def poll(self, last_seen_marker: LastSeenMarker) -> AdapterPollResult:
        raise NotImplementedError(f"{self.adapter_type} adapter is not implemented")


def pending_adapter_factory(adapter_type: str) -> AdapterFactory:
    def _factory(config: AdapterConfig) -> SourceAdapter:
        return PendingAdapter(config.adapter_type)

    return _factory


def adapter_error_from_exception(
    exc: Exception, *, url: str | None = None
) -> AdapterItemError:
    return AdapterItemError(error=str(exc), url=url)


def _accepts_ingestion_config(factory: AdapterFactory) -> bool:
    parameters = signature(factory).parameters.values()
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
    ]
    has_varargs = any(
        parameter.kind == Parameter.VAR_POSITIONAL for parameter in parameters
    )
    return has_varargs or len(positional) >= 2
