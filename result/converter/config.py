"""Validated configuration and named profiles for the MHTML converter."""

from __future__ import annotations

import codecs
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .parser import Resource
    from .plugins import ConverterPlugin


class ConversionProfile(str, Enum):
    """Built-in conversion presets."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"
    SECURE = "secure"
    OPTIMIZED = "optimized"


ResourceHandler = Callable[["Resource"], "Resource | bytes | str | None"]
ProgressCallback = Callable[[str, float], None]


# The public configuration intentionally groups many independent knobs in one object.
# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class ConverterConfig:
    """Options controlling parsing, rewriting, fetching, and output.

    External fetching is disabled by default. Enable it only when converting
    trusted documents; even with it enabled, only public HTTP(S) resources are
    fetched and optional domain allow/deny lists are enforced.
    """

    profile: ConversionProfile = ConversionProfile.STANDARD
    output_format: str = "html5"
    encoding: str = "utf-8"
    resource_handling: str = "inline"
    max_resource_size: int = 10 * 1024 * 1024
    max_input_size: int = 128 * 1024 * 1024
    fetch_external: bool = False
    fetch_timeout: float = 10.0
    max_fetch_retries: int = 2
    include_scripts: bool = True
    include_styles: bool = True
    minify_html: bool = False
    minify_css: bool = False
    compress_output: bool = False
    sanitize_html: bool = True
    remove_scripts: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    parallel_processing: bool = True
    max_workers: int = 4
    streaming_output: bool = False
    chunk_size: int = 64 * 1024
    custom_handlers: dict[str, ResourceHandler] = field(default_factory=dict)
    plugins: list[ConverterPlugin] = field(default_factory=list)
    metadata_extraction: bool = True
    progress_callback: ProgressCallback | None = None
    error_recovery: bool = True
    validation: bool = True
    strip_css_comments: bool = True
    max_import_depth: int = 10
    cache_enabled: bool = True
    cache_size: int = 100
    cache_dir: Path | None = None
    debug_mode: bool = False
    log_level: str = "INFO"
    log_file: Path | None = None

    def __post_init__(self) -> None:
        """Normalize user-friendly values, apply presets, and validate options."""
        if isinstance(self.profile, str):
            self.profile = ConversionProfile(self.profile.lower())
        if self.profile is not ConversionProfile.STANDARD:
            self.apply_profile(self.profile)
        if self.cache_dir is not None:
            self.cache_dir = Path(self.cache_dir)
        if self.log_file is not None:
            self.log_file = Path(self.log_file)
        self.allowed_domains = [
            domain.strip().lower().strip(".") for domain in self.allowed_domains
        ]
        self.blocked_domains = [
            domain.strip().lower().strip(".") for domain in self.blocked_domains
        ]
        self.validate()

    def apply_profile(self, profile: ConversionProfile) -> None:
        """Apply the named preset; callers may customize fields afterward."""
        if isinstance(profile, str):
            profile = ConversionProfile(profile.lower())
        self.profile = profile

        shared = {
            "remove_scripts": False,
            "include_scripts": True,
            "include_styles": True,
            "sanitize_html": True,
            "resource_handling": "inline",
            "parallel_processing": True,
            "debug_mode": False,
        }
        presets: dict[ConversionProfile, dict[str, Any]] = {
            ConversionProfile.MINIMAL: {
                **shared,
                "minify_html": True,
                "minify_css": True,
                "compress_output": True,
                "fetch_external": False,
                "include_scripts": False,
                "include_styles": False,
                "max_workers": 1,
                "log_level": "WARNING",
            },
            ConversionProfile.STANDARD: {
                **shared,
                "minify_html": False,
                "minify_css": False,
                "compress_output": False,
                "fetch_external": False,
                "max_workers": 4,
                "log_level": "INFO",
            },
            ConversionProfile.FULL: {
                **shared,
                "minify_html": False,
                "minify_css": False,
                "compress_output": False,
                "fetch_external": True,
                "resource_handling": "mixed",
                "max_workers": 8,
                "debug_mode": True,
                "log_level": "DEBUG",
            },
            ConversionProfile.SECURE: {
                **shared,
                "minify_html": True,
                "minify_css": True,
                "compress_output": True,
                "fetch_external": False,
                "remove_scripts": True,
                "include_scripts": False,
                "include_styles": False,
                "parallel_processing": False,
                "max_workers": 1,
                "log_level": "WARNING",
            },
            ConversionProfile.OPTIMIZED: {
                **shared,
                "minify_html": True,
                "minify_css": True,
                "compress_output": True,
                "fetch_external": False,
                "max_workers": 8,
                "log_level": "INFO",
            },
        }
        for name, value in presets[profile].items():
            setattr(self, name, value)

    def validate(self) -> None:
        """Raise ``ValueError`` when a setting is invalid or unsafe."""
        if self.output_format not in {"html5", "xhtml"}:
            raise ValueError("output_format must be 'html5' or 'xhtml'")
        if self.resource_handling not in {"inline", "external", "mixed"}:
            raise ValueError(
                "resource_handling must be 'inline', 'external', or 'mixed'"
            )
        try:
            codecs.lookup(self.encoding)
        except LookupError as error:
            raise ValueError(f"Unknown output encoding: {self.encoding}") from error
        if self.max_resource_size <= 0 or self.max_input_size <= 0:
            raise ValueError("max_resource_size and max_input_size must be positive")
        if self.fetch_timeout <= 0:
            raise ValueError("fetch_timeout must be positive")
        if self.max_fetch_retries < 0:
            raise ValueError("max_fetch_retries cannot be negative")
        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        if self.max_import_depth < 0:
            raise ValueError("max_import_depth cannot be negative")
        if self.cache_size < 0:
            raise ValueError("cache_size cannot be negative")
        if self.log_level.upper() not in {
            "TRACE",
            "DEBUG",
            "INFO",
            "SUCCESS",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            raise ValueError(f"Unsupported log level: {self.log_level}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of configuration settings."""
        values: dict[str, Any] = {
            config_field.name: getattr(self, config_field.name)
            for config_field in fields(self)
        }
        values["profile"] = self.profile.value
        values["allowed_domains"] = list(self.allowed_domains)
        values["blocked_domains"] = list(self.blocked_domains)
        values["cache_dir"] = str(self.cache_dir) if self.cache_dir else None
        values["log_file"] = str(self.log_file) if self.log_file else None
        values["custom_handlers"] = sorted(self.custom_handlers)
        values["plugins"] = [type(plugin).__name__ for plugin in self.plugins]
        values["progress_callback"] = self.progress_callback is not None
        return values


__all__ = [
    "ConversionProfile",
    "ConverterConfig",
    "ProgressCallback",
    "ResourceHandler",
]
