"""MHTML-to-HTML orchestration, resource resolution, validation, and file output."""

from __future__ import annotations

import html as html_stdlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Self
from urllib.parse import urlsplit

from .config import ConversionProfile, ConverterConfig, ProgressCallback
from .css_processor import CSSProcessor
from .html_processor import HTMLProcessor
from .logger import ConverterLogger
from .parser import MHTMLParser, Resource, ResourceType
from .resource_manager import ResourceManager


@dataclass(slots=True)
class _ParsedDocument:
    """Internal aggregate of the selected MIME part and its companion assets."""

    main_resource: Resource
    resources: dict[str, Resource]
    metadata: dict[str, Any]


@dataclass(slots=True)
class _CSSRewriteState:
    """Mutable traversal state for recursive CSS rewriting and cycle detection."""

    resource_map: dict[str, Resource]
    fallback_base: str
    visiting: set[int] = field(default_factory=set)
    processed: set[int] = field(default_factory=set)


class MHTMLConverter:
    """Coordinate MIME parsing, resource processing, rewriting, and output."""

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Create a converter and its stateful cache/resource services."""
        self.config = config or ConverterConfig()
        self.logger = ConverterLogger(self.config)
        self.parser = MHTMLParser(self.config)
        self.resource_manager = ResourceManager(self.config)
        self.html_processor = HTMLProcessor(self.config)
        self.css_processor = CSSProcessor(self.config)

    def __enter__(self) -> Self:
        """Allow use as a context manager for timely logger cleanup."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Release this converter's optional Loguru file sink."""
        self.close()

    def close(self) -> None:
        """Close this converter's optional logging sink."""
        self.logger.close()

    def convert(
        self,
        mhtml_data: bytes | str,
        base_url: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        """Convert in-memory MHTML data to HTML bytes and a metadata dictionary.

        The parser retains MIME part payloads in memory. ``max_input_size`` and
        ``max_resource_size`` provide predictable bounds; use ``convert_stream``
        or ``convert_file`` to write the final output incrementally.
        """
        callback = (
            progress_callback
            if progress_callback is not None
            else self.config.progress_callback
        )
        previous_callback = self.logger.progress_callback
        self.logger.set_progress_callback(callback)
        try:
            return self._convert(mhtml_data, base_url)
        finally:
            self.logger.set_progress_callback(previous_callback)

    def _convert(
        self,
        mhtml_data: bytes | str,
        base_url: str | None,
    ) -> tuple[bytes, dict[str, Any]]:
        raw_data = (
            mhtml_data.encode(self.config.encoding)
            if isinstance(mhtml_data, str)
            else mhtml_data
        )
        if len(raw_data) > self.config.max_input_size:
            raise ValueError(
                f"MHTML input exceeds the {self.config.max_input_size}-byte limit"
            )

        self.logger.info("Starting MHTML conversion")
        self.logger.debug(f"Configuration: {self.config.to_dict()}")
        self.logger.log_progress("Parsing MHTML", 0.1)
        try:
            prepared_data = self._run_before_parse_plugins(raw_data)
            main_resource, resources, metadata = self.parser.parse_mhtml(prepared_data)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.logger.exception("MHTML parsing or input plugin failed")
            if not self.config.error_recovery:
                raise
            return self._fallback_conversion(raw_data, error)

        parsed = _ParsedDocument(main_resource, resources, metadata)
        return self._convert_parsed(raw_data, parsed, base_url)

    def _convert_parsed(
        self,
        raw_data: bytes,
        parsed: _ParsedDocument,
        base_url: str | None,
    ) -> tuple[bytes, dict[str, Any]]:
        main_resource = parsed.main_resource
        resolved_base = self._resolve_base_url(base_url, main_resource.url)
        resource_map = self._normalize_resource_map(parsed.resources, resolved_base)
        self.logger.log_progress("Processing resources", 0.3)

        main_content = self._resource_text(main_resource)
        assets = self._extract_main_asset_urls(main_resource, main_content)
        self._fetch_missing_resources(assets, resolved_base, resource_map)
        self._fetch_nested_css_resources(main_resource, resource_map, resolved_base)
        self._apply_resource_plugins(resource_map)
        self._rewrite_css_resources(resource_map, resolved_base)

        self.logger.log_progress("Rewriting main content", 0.6)
        output = self._render_main_resource(
            main_resource,
            main_content,
            resolved_base,
            resource_map,
        )
        output = self._run_after_convert_plugins(output, parsed.metadata)
        validation = self._validate_output(output, main_resource.resource_type)
        self.logger.log_progress("Validating and finalizing output", 0.9)

        metadata: dict[str, Any] = {
            "original_size": len(raw_data),
            "output_size": len(output),
            "resource_count": len(self._unique_resources(resource_map.values())),
            "main_resource_type": main_resource.resource_type.value,
            "content_type": main_resource.content_type,
            "profile": self.config.profile.value,
            "metadata": parsed.metadata,
            "config": self.config.to_dict(),
            "validation": validation,
            "output_format": self.config.output_format,
        }
        self.logger.log_progress("Conversion complete", 1.0)
        self.logger.info("MHTML conversion completed successfully")
        return output, metadata

    def _resolve_base_url(self, base_url: str | None, resource_url: str) -> str:
        """Use a caller URL or the main part's URL when it is a valid HTTP base."""
        if base_url:
            return base_url
        if resource_url and urlsplit(resource_url).scheme.lower() in {"http", "https"}:
            return resource_url
        return "http://localhost/"

    def _render_main_resource(
        self,
        main_resource: Resource,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> bytes:
        """Rewrite a main HTML/CSS part and encode its output."""
        if main_resource.resource_type == ResourceType.HTML:
            rewritten = self.html_processor.rewrite_html(
                content, base_url, resource_map
            )
            if self.config.minify_html or self.config.compress_output:
                rewritten = self.html_processor.minify_html(rewritten)
            return rewritten.encode(self.config.encoding, errors="replace")
        if main_resource.resource_type == ResourceType.CSS:
            rewritten = self.css_processor.rewrite_css(content, base_url, resource_map)
            return rewritten.encode(self.config.encoding, errors="replace")
        if isinstance(main_resource.content, bytes):
            return main_resource.content
        return main_resource.content.encode(self.config.encoding, errors="replace")

    def convert_file(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        base_url: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Convert a file, writing ``<input-stem>.html`` beside it by default."""
        source = Path(input_path)
        if not source.is_file():
            raise FileNotFoundError(f"Input MHTML file does not exist: {source}")
        if source.stat().st_size > self.config.max_input_size:
            raise ValueError(
                f"MHTML input exceeds the {self.config.max_input_size}-byte limit"
            )
        destination = (
            Path(output_path)
            if output_path is not None
            else source.with_suffix(".html")
        )
        if source.resolve() == destination.resolve():
            raise ValueError("Output path must not overwrite the input MHTML file")

        with source.open("rb") as input_file:
            result, metadata = self.convert(
                input_file.read(self.config.max_input_size + 1),
                base_url=base_url,
                progress_callback=progress_callback,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            for chunk in self._chunks(result):
                output_file.write(chunk)
        metadata["output_path"] = str(destination)
        return destination, metadata

    def convert_stream(
        self,
        source: BinaryIO,
        destination: BinaryIO,
        base_url: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Read an input stream within limits and write output in bounded chunks.

        The MIME parser needs a complete message for reliable related-part
        lookup, so input is buffered up to ``max_input_size``; output is written
        incrementally according to ``chunk_size``.
        """
        input_buffer = bytearray()
        while True:
            next_chunk = source.read(self.config.chunk_size)
            if not next_chunk:
                break
            input_buffer.extend(next_chunk)
            if len(input_buffer) > self.config.max_input_size:
                raise ValueError(
                    f"MHTML input exceeds the {self.config.max_input_size}-byte limit"
                )
        result, metadata = self.convert(
            bytes(input_buffer),
            base_url=base_url,
            progress_callback=progress_callback,
        )
        destination.writelines(self._chunks(result))
        return metadata

    def iter_convert(
        self,
        mhtml_data: bytes | str,
        base_url: str | None = None,
    ) -> Iterator[bytes]:
        """Yield the converted output in ``chunk_size`` byte pieces."""
        output, _metadata = self.convert(mhtml_data, base_url=base_url)
        yield from self._chunks(output)

    def _chunks(self, content: bytes) -> Iterator[bytes]:
        for offset in range(0, len(content), self.config.chunk_size):
            yield content[offset : offset + self.config.chunk_size]

    def _run_before_parse_plugins(self, data: bytes) -> bytes:
        """Run each plugin's input hook in the order it was registered."""
        for plugin in self.config.plugins:
            data = plugin.before_parse(data, self.config)
            if not isinstance(data, bytes):
                raise TypeError("plugin before_parse hooks must return bytes")
        return data

    def _run_after_convert_plugins(
        self,
        output: bytes,
        metadata: dict[str, Any],
    ) -> bytes:
        """Run each plugin's output hook in registration order."""
        for plugin in self.config.plugins:
            output = plugin.after_convert(output, metadata)
            if not isinstance(output, bytes):
                raise TypeError("plugin after_convert hooks must return bytes")
        return output

    def _normalize_resource_map(
        self,
        resources: dict[str, Resource],
        base_url: str,
    ) -> dict[str, Resource]:
        """Canonicalize MIME resource keys and apply custom resource handlers."""
        normalized: dict[str, Resource] = {}
        transformed_by_id: dict[int, Resource] = {}
        for key, resource in resources.items():
            transformed = transformed_by_id.get(id(resource))
            if transformed is None:
                transformed = self.resource_manager.transform_resource(resource)
                transformed_by_id[id(resource)] = transformed
            if key.lower().startswith(("cid:", "data:")):
                normalized[key] = transformed
            else:
                normalized[self.resource_manager.normalize_url(key, base_url)] = (
                    transformed
                )
            if resource.url:
                if resource.url.lower().startswith(("cid:", "data:")):
                    normalized[resource.url] = transformed
                else:
                    normalized[
                        self.resource_manager.normalize_url(resource.url, base_url)
                    ] = transformed
        return normalized

    def _extract_main_asset_urls(
        self,
        main_resource: Resource,
        content: str,
    ) -> set[str]:
        """Discover fetchable HTML/CSS assets, excluding ordinary anchor links."""
        if main_resource.resource_type == ResourceType.HTML:
            return self.html_processor.extract_resource_urls(content)
        if main_resource.resource_type == ResourceType.CSS:
            return self.css_processor.extract_urls(content)
        return set()

    def _fetch_missing_resources(
        self,
        urls: set[str],
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> None:
        """Fetch external assets only when not already present in the MIME map."""
        missing = [
            self.resource_manager.normalize_url(url, base_url)
            for url in urls
            if self.resource_manager.normalize_url(url, base_url) not in resource_map
        ]
        fetched = self.resource_manager.process_resources_parallel(missing, base_url)
        resource_map.update(
            (url, resource) for url, resource in fetched.items() if resource is not None
        )

    def _fetch_nested_css_resources(
        self,
        main_resource: Resource,
        resource_map: dict[str, Resource],
        base_url: str,
    ) -> None:
        """Resolve nested CSS URLs/imports iteratively up to the configured depth."""
        css_resources = [
            resource
            for resource in self._unique_resources(resource_map.values())
            if resource.resource_type == ResourceType.CSS
        ]
        if main_resource.resource_type == ResourceType.CSS:
            css_resources.append(main_resource)

        for _ in range(self.config.max_import_depth):
            pending = self._find_missing_css_urls(css_resources, resource_map, base_url)
            if not pending:
                return
            added = self._fetch_resource_batch(pending, base_url, resource_map)
            if not added:
                return
            css_resources.extend(
                resource
                for resource in added
                if resource.resource_type == ResourceType.CSS
            )

    def _find_missing_css_urls(
        self,
        css_resources: Iterable[Resource],
        resource_map: dict[str, Resource],
        fallback_base: str,
    ) -> set[str]:
        """Collect uncached CSS URLs with each stylesheet's own base URL."""
        pending: set[str] = set()
        for resource in css_resources:
            css_base = resource.url or fallback_base
            for raw_url in self.css_processor.extract_urls(
                self._resource_text(resource)
            ):
                normalized = self.resource_manager.normalize_url(raw_url, css_base)
                if normalized not in resource_map and not normalized.lower().startswith(
                    ("data:", "cid:")
                ):
                    pending.add(normalized)
        return pending

    def _fetch_resource_batch(
        self,
        urls: set[str],
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> list[Resource]:
        """Fetch unresolved CSS dependencies and add successful responses to the map."""
        fetched = self.resource_manager.process_resources_parallel(
            sorted(urls), base_url
        )
        added = [resource for resource in fetched.values() if resource is not None]
        resource_map.update(
            (url, resource) for url, resource in fetched.items() if resource is not None
        )
        return added

    def _apply_resource_plugins(self, resource_map: dict[str, Resource]) -> None:
        """Apply resource hooks once per unique MIME resource and preserve aliases."""
        transformed: dict[int, Resource] = {}
        for key, resource in list(resource_map.items()):
            replacement = transformed.get(id(resource))
            if replacement is None:
                replacement = resource
                for plugin in self.config.plugins:
                    replacement = plugin.process_resource(replacement)
                    if not isinstance(replacement, Resource):
                        raise TypeError(
                            "plugin process_resource hooks must return Resource"
                        )
                transformed[id(resource)] = replacement
            resource_map[key] = replacement

    def _rewrite_css_resources(
        self,
        resource_map: dict[str, Resource],
        base_url: str,
    ) -> None:
        """Rewrite CSS assets recursively, guarding cycles and import depth."""
        state = _CSSRewriteState(resource_map, base_url)
        for resource in self._unique_resources(resource_map.values()):
            if resource.resource_type == ResourceType.CSS:
                self._rewrite_css_resource(resource, state, 0)

    def _rewrite_css_resource(
        self,
        resource: Resource,
        state: _CSSRewriteState,
        depth: int,
    ) -> None:
        """Rewrite one stylesheet after rewriting mapped CSS dependencies."""
        identity = id(resource)
        if identity in state.processed or identity in state.visiting:
            return
        state.visiting.add(identity)
        css_text = self._resource_text(resource)
        css_base = resource.url or state.fallback_base
        if depth < self.config.max_import_depth:
            self._rewrite_css_dependencies(css_text, state, css_base, depth)

        safe_map = {
            key: value
            for key, value in state.resource_map.items()
            if id(value) not in state.visiting
        }
        rewritten = self.css_processor.rewrite_css(
            css_text,
            css_base,
            safe_map,
            depth=depth,
        )
        resource.content = rewritten.encode(self.config.encoding, errors="replace")
        resource.size = len(resource.content)
        state.visiting.remove(identity)
        state.processed.add(identity)

    def _rewrite_css_dependencies(
        self,
        css_text: str,
        state: _CSSRewriteState,
        css_base: str,
        depth: int,
    ) -> None:
        """Rewrite all mapped stylesheet dependencies before their parent."""
        for raw_url in self.css_processor.extract_urls(css_text):
            normalized = self.resource_manager.normalize_url(raw_url, css_base)
            dependency = state.resource_map.get(normalized)
            if dependency and dependency.resource_type == ResourceType.CSS:
                self._rewrite_css_resource(dependency, state, depth + 1)

    def _resource_text(self, resource: Resource) -> str:
        """Decode textual MIME content using its part-level charset and BOM."""
        content_type = resource.headers.get("Content-Type", resource.content_type)
        return self.parser.decode_text(resource.content, content_type)

    def _validate_output(
        self,
        output: bytes,
        resource_type: ResourceType,
    ) -> dict[str, Any]:
        """Validate generated HTML/CSS and return actionable diagnostics."""
        if not self.config.validation:
            return {"enabled": False, "valid": True, "errors": []}
        if resource_type == ResourceType.HTML:
            text = self.parser.decode_text(output, self.config.encoding)
            errors = self.html_processor.validate_html(text)
        elif resource_type == ResourceType.CSS:
            text = self.parser.decode_text(output, self.config.encoding)
            rules = self.css_processor.parse_css(text)
            errors = [
                str(rule) for rule in rules if getattr(rule, "type", "") == "error"
            ]
        else:
            errors = []
        return {"enabled": True, "valid": not errors, "errors": errors}

    def _fallback_conversion(
        self,
        data: bytes,
        error: Exception,
    ) -> tuple[bytes, dict[str, Any]]:
        """Recover invalid MHTML into safe HTML rather than returning a broken MIME file."""
        text = data.decode(self.config.encoding, errors="replace")
        start = text.lower().find("<html")
        end = text.lower().rfind("</html>")
        if 0 <= start <= end:
            recovered = text[start : end + len("</html>")]
            safe_html = self.html_processor.rewrite_html(
                recovered,
                "http://localhost/",
                {},
            )
            output = safe_html.encode(self.config.encoding, errors="replace")
        else:
            safe_text = html_stdlib.escape(text, quote=False)
            output = (
                '<!doctype html><html><head><meta charset="utf-8"></head>'
                f"<body><pre>{safe_text}</pre></body></html>"
            ).encode()
        validation = self._validate_output(output, ResourceType.HTML)
        metadata = {
            "original_size": len(data),
            "output_size": len(output),
            "resource_count": 0,
            "main_resource_type": "other",
            "content_type": "text/html",
            "profile": self.config.profile.value,
            "metadata": {},
            "config": self.config.to_dict(),
            "validation": validation,
            "output_format": self.config.output_format,
            "error": str(error),
        }
        self.logger.warning(f"Returning recovered HTML after parse error: {error}")
        self.logger.log_progress("Conversion recovered", 1.0)
        return output, metadata

    @staticmethod
    def _unique_resources(resources: Iterable[Resource]) -> list[Resource]:
        """Return resources once even when the map has URL and CID aliases."""
        unique: list[Resource] = []
        seen: set[int] = set()
        for resource in resources:
            identity = id(resource)
            if identity not in seen:
                unique.append(resource)
                seen.add(identity)
        return unique


__all__ = ["ConversionProfile", "ConverterConfig", "MHTMLConverter"]
