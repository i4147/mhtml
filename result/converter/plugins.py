"""Small, dependency-free plugin hooks for conversion customization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ConverterConfig
    from .parser import Resource


class ConverterPlugin:
    """Base class for optional converter extensions.

    Subclasses can override any hook. Hooks run in registration order. The
    default implementations leave data untouched.
    """

    def before_parse(self, data: bytes, config: ConverterConfig) -> bytes:
        """Transform MHTML bytes before parsing."""
        del config
        return data

    def process_resource(self, resource: Resource) -> Resource:
        """Transform an extracted resource before it is rewritten into HTML."""
        return resource

    def after_convert(self, output: bytes, metadata: dict[str, Any]) -> bytes:
        """Transform final output bytes after conversion and validation."""
        del metadata
        return output


__all__ = ["ConverterPlugin"]
